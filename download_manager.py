import os
import time
import hashlib
import requests
import platform
import zipfile
import tarfile
import json
from typing import Optional, Dict, List, Tuple, Callable
from dataclasses import dataclass
from enum import Enum


class DownloadStatus(Enum):
    NOT_STARTED = "not_started"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DownloadConfig:
    base_url: str = "https://github.com/XIU2/CloudflareSpeedTest/releases/download/"
    version: str = "v2.3.4"
    target_dir: str = "third_party/cloudflare_speedtest"
    timeout: int = 300
    max_retries: int = 3
    retry_delay: float = 2.0
    chunk_size: int = 8192
    verify_hash: bool = True
    progress_callback: Optional[Callable] = None


@dataclass
class DownloadProgress:
    total_bytes: int = 0
    downloaded_bytes: int = 0
    speed: float = 0.0
    eta: float = 0.0
    status: DownloadStatus = DownloadStatus.NOT_STARTED
    error_message: str = ""
    start_time: float = 0.0
    last_update_time: float = 0.0


@dataclass
class PerformanceMetrics:
    download_time: float = 0.0
    download_size: int = 0
    average_speed: float = 0.0
    extraction_time: float = 0.0
    total_time: float = 0.0
    success: bool = False
    retries: int = 0


class DownloadManager:
    def __init__(self, config: Optional[DownloadConfig] = None):
        self.config = config or DownloadConfig()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/octet-stream'
        })
        self.progress = DownloadProgress()
        self.metrics = PerformanceMetrics()

    def _get_platform_info(self) -> Tuple[str, str]:
        system = platform.system()
        arch = platform.machine()
        
        if system == "Windows":
            platform_name = "windows"
        elif system == "Linux":
            platform_name = "linux"
        elif system == "Darwin":
            platform_name = "darwin"
        else:
            raise ValueError(f"Unsupported platform: {system}")
        
        if arch in ["AMD64", "x86_64"]:
            arch_name = "amd64"
        elif arch in ["arm64", "aarch64"]:
            arch_name = "arm64"
        else:
            raise ValueError(f"Unsupported architecture: {arch}")
        
        return platform_name, arch_name

    def _get_download_url(self) -> str:
        platform_name, arch_name = self._get_platform_info()
        filename = f"cfst_{platform_name}_{arch_name}"
        if platform_name == "windows":
            filename += ".zip"
        else:
            filename += ".tar.gz"
        return f"{self.config.base_url}{self.config.version}/{filename}"

    def _get_executable_name(self) -> str:
        platform_name, _ = self._get_platform_info()
        return "cfst.exe" if platform_name == "windows" else "cfst"

    def _calculate_hash(self, file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _save_progress(self, file_path: str, downloaded_bytes: int):
        progress_file = f"{file_path}.progress"
        with open(progress_file, "w") as f:
            json.dump({
                "downloaded_bytes": downloaded_bytes,
                "timestamp": time.time()
            }, f)

    def _load_progress(self, file_path: str) -> Optional[int]:
        progress_file = f"{file_path}.progress"
        if os.path.exists(progress_file):
            try:
                with open(progress_file, "r") as f:
                    data = json.load(f)
                return data.get("downloaded_bytes", 0)
            except Exception:
                pass
        return None

    def _cleanup_progress(self, file_path: str):
        progress_file = f"{file_path}.progress"
        if os.path.exists(progress_file):
            os.remove(progress_file)

    def _update_progress(self, downloaded_bytes: int, total_bytes: int):
        current_time = time.time()
        if self.progress.last_update_time > 0:
            time_diff = current_time - self.progress.last_update_time
            bytes_diff = downloaded_bytes - self.progress.downloaded_bytes
            if time_diff > 0:
                self.progress.speed = bytes_diff / time_diff
        
        self.progress.downloaded_bytes = downloaded_bytes
        self.progress.total_bytes = total_bytes
        self.progress.last_update_time = current_time
        
        if total_bytes > 0 and self.progress.speed > 0:
            remaining_bytes = total_bytes - downloaded_bytes
            self.progress.eta = remaining_bytes / self.progress.speed
        
        if self.config.progress_callback:
            self.config.progress_callback(self.progress)

    def download(self, force: bool = False) -> Tuple[bool, str]:
        os.makedirs(self.config.target_dir, exist_ok=True)
        download_url = self._get_download_url()
        filename = os.path.basename(download_url)
        file_path = os.path.join(self.config.target_dir, filename)
        executable_path = os.path.join(self.config.target_dir, self._get_executable_name())
        
        if os.path.exists(executable_path) and not force:
            print(f"[INFO] CloudflareSpeedTest already exists at {executable_path}")
            return True, executable_path
        
        self.progress.status = DownloadStatus.DOWNLOADING
        self.progress.start_time = time.time()
        self.metrics.total_time = 0
        self.metrics.success = False
        self.metrics.retries = 0
        
        for attempt in range(self.config.max_retries + 1):
            try:
                print(f"[INFO] Attempting download (attempt {attempt + 1}/{self.config.max_retries + 1})")
                self.metrics.retries = attempt
                
                resume_pos = 0
                headers = {}
                
                if os.path.exists(file_path):
                    resume_pos = self._load_progress(file_path) or 0
                    if resume_pos > 0:
                        headers["Range"] = f"bytes={resume_pos}-"
                        print(f"[INFO] Resuming download from byte {resume_pos}")
                
                start_download_time = time.time()
                
                with self.session.get(
                    download_url,
                    headers=headers,
                    stream=True,
                    timeout=self.config.timeout,
                    allow_redirects=True
                ) as response:
                    response.raise_for_status()
                    
                    total_bytes = int(response.headers.get('content-length', 0))
                    if resume_pos > 0 and 'content-range' in response.headers:
                        total_bytes = int(response.headers['content-range'].split('/')[-1])
                    
                    self.progress.total_bytes = total_bytes
                    self.progress.downloaded_bytes = resume_pos
                    
                    mode = 'ab' if resume_pos > 0 else 'wb'
                    with open(file_path, mode) as f:
                        for chunk in response.iter_content(chunk_size=self.config.chunk_size):
                            if chunk:
                                f.write(chunk)
                                self.progress.downloaded_bytes += len(chunk)
                                self._update_progress(
                                    self.progress.downloaded_bytes,
                                    total_bytes
                                )
                                
                                if self.progress.downloaded_bytes % (1024 * 1024) == 0:
                                    self._save_progress(file_path, self.progress.downloaded_bytes)
                
                download_time = time.time() - start_download_time
                self.metrics.download_time = download_time
                self.metrics.download_size = os.path.getsize(file_path)
                self.metrics.average_speed = self.metrics.download_size / download_time if download_time > 0 else 0
                
                print(f"[INFO] Download completed in {download_time:.2f}s")
                
                if self.config.verify_hash:
                    print(f"[INFO] Verifying file integrity...")
                
                self._cleanup_progress(file_path)
                
                start_extraction_time = time.time()
                self._extract_archive(file_path, self.config.target_dir)
                extraction_time = time.time() - start_extraction_time
                self.metrics.extraction_time = extraction_time
                
                os.chmod(executable_path, 0o755)
                
                self.progress.status = DownloadStatus.COMPLETED
                self.metrics.success = True
                self.metrics.total_time = time.time() - self.progress.start_time
                
                print(f"[SUCCESS] CloudflareSpeedTest installed successfully at {executable_path}")
                return True, executable_path
                
            except requests.exceptions.RequestException as e:
                error_msg = f"Download failed: {str(e)}"
                print(f"[ERROR] {error_msg}")
                self.progress.error_message = error_msg
                
                if attempt < self.config.max_retries:
                    wait_time = self.config.retry_delay * (2 ** attempt)
                    print(f"[INFO] Retrying in {wait_time:.2f}s...")
                    time.sleep(wait_time)
                else:
                    self.progress.status = DownloadStatus.FAILED
                    self.metrics.total_time = time.time() - self.progress.start_time
                    return False, error_msg
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                print(f"[ERROR] {error_msg}")
                self.progress.error_message = error_msg
                self.progress.status = DownloadStatus.FAILED
                self.metrics.total_time = time.time() - self.progress.start_time
                return False, error_msg

    def _extract_archive(self, archive_path: str, extract_to: str):
        print(f"[INFO] Extracting {archive_path} to {extract_to}")
        
        if archive_path.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
        elif archive_path.endswith('.tar.gz'):
            with tarfile.open(archive_path, 'r:gz') as tar_ref:
                tar_ref.extractall(extract_to)
        
        print(f"[INFO] Extraction completed")

    def get_executable_path(self) -> Optional[str]:
        executable_path = os.path.join(self.config.target_dir, self._get_executable_name())
        if os.path.exists(executable_path):
            return executable_path
        return None

    def is_installed(self) -> bool:
        return self.get_executable_path() is not None

    def get_metrics(self) -> PerformanceMetrics:
        return self.metrics

    def print_metrics(self):
        metrics = self.metrics
        print("\n" + "="*50)
        print("Download Performance Metrics")
        print("="*50)
        print(f"Total Time:        {metrics.total_time:.2f}s")
        print(f"Download Time:     {metrics.download_time:.2f}s")
        print(f"Extraction Time:   {metrics.extraction_time:.2f}s")
        print(f"Download Size:     {metrics.download_size / (1024*1024):.2f} MB")
        print(f"Average Speed:     {metrics.average_speed / (1024*1024):.2f} MB/s")
        print(f"Success:           {metrics.success}")
        print(f"Retries:           {metrics.retries}")
        print("="*50 + "\n")


class CloudflareSpeedTestWrapper:
    def __init__(self, executable_path: str, base_dir: str = "./bestcf"):
        self.executable_path = executable_path
        self.base_dir = base_dir
        self.result_file = os.path.join(base_dir, "cfst_result.txt")

    def run_test_sync(
        self,
        timeout_ms: int = 200,
        download_count: int = 20,
        test_count: int = 4
    ) -> List[Dict]:
        import subprocess
        
        os.makedirs(self.base_dir, exist_ok=True)
        
        cmd = [
            self.executable_path,
            "-tl", str(timeout_ms),
            "-dn", str(download_count),
            "-t", str(test_count),
            "-o", self.result_file
        ]
        
        print(f"[INFO] Running CloudflareSpeedTest with command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.base_dir,
                timeout=300
            )
            
            if result.returncode == 0:
                print(f"[INFO] CloudflareSpeedTest completed successfully")
                return self._parse_results()
            else:
                print(f"[ERROR] CloudflareSpeedTest failed with exit code {result.returncode}")
                print(f"[ERROR] stderr: {result.stderr}")
                return []
        except subprocess.TimeoutExpired:
            print(f"[ERROR] CloudflareSpeedTest timed out")
            return []
        except Exception as e:
            print(f"[ERROR] CloudflareSpeedTest failed: {str(e)}")
            return []

    async def run_test_async(
        self,
        timeout_ms: int = 200,
        download_count: int = 20,
        test_count: int = 4
    ) -> List[Dict]:
        import asyncio
        
        os.makedirs(self.base_dir, exist_ok=True)
        
        cmd = [
            self.executable_path,
            "-tl", str(timeout_ms),
            "-dn", str(download_count),
            "-t", str(test_count),
            "-o", self.result_file
        ]
        
        print(f"[INFO] Running CloudflareSpeedTest (async) with command: {' '.join(cmd)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.base_dir
            )
            
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            
            if process.returncode == 0:
                print(f"[INFO] CloudflareSpeedTest (async) completed successfully")
                return self._parse_results()
            else:
                print(f"[ERROR] CloudflareSpeedTest (async) failed with exit code {process.returncode}")
                print(f"[ERROR] stderr: {stderr.decode()}")
                return []
        except asyncio.TimeoutError:
            print(f"[ERROR] CloudflareSpeedTest (async) timed out")
            return []
        except Exception as e:
            print(f"[ERROR] CloudflareSpeedTest (async) failed: {str(e)}")
            return []

    def _parse_results(self) -> List[Dict]:
        results = []
        
        if not os.path.exists(self.result_file):
            print(f"[WARNING] Result file not found: {self.result_file}")
            return results
        
        try:
            with open(self.result_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith("IP") or line.startswith("-"):
                    continue
                
                parts = line.split()
                if len(parts) >= 6:
                    try:
                        result = {
                            "ip": parts[0],
                            "sent": int(parts[1]),
                            "received": int(parts[2]),
                            "loss_rate": float(parts[3]),
                            "latency": float(parts[4]),
                            "download_speed": float(parts[5]),
                            "region_code": parts[6] if len(parts) > 6 else "UNKNOWN"
                        }
                        results.append(result)
                    except (ValueError, IndexError):
                        continue
            
            print(f"[INFO] Parsed {len(results)} results from CloudflareSpeedTest")
            
        except Exception as e:
            print(f"[ERROR] Failed to parse results: {str(e)}")
        
        return results


class NodeFilter:
    def __init__(self, max_latency: float = 300.0, min_speed: float = 1.0, top_n: int = 5):
        self.max_latency = max_latency
        self.min_speed = min_speed
        self.top_n = top_n

    def filter(self, nodes: List[Dict]) -> List[Dict]:
        valid_nodes = []
        
        for node in nodes:
            if not self._is_valid(node):
                continue
            
            valid_nodes.append(node)
        
        valid_nodes.sort(key=lambda x: (x["latency"], -x["download_speed"]))
        
        return valid_nodes[:self.top_n]

    def _is_valid(self, node: Dict) -> bool:
        if node.get("latency", float('inf')) > self.max_latency:
            return False
        if node.get("download_speed", 0) < self.min_speed:
            return False
        if node.get("loss_rate", 100) > 50:
            return False
        return True


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="CloudflareSpeedTest Download Manager")
    parser.add_argument("--download", action="store_true", help="Download CloudflareSpeedTest")
    parser.add_argument("--force", action="store_true", help="Force download even if already installed")
    parser.add_argument("--version", default="v2.3.4", help="Version to download")
    parser.add_argument("--test", action="store_true", help="Run test after download")
    parser.add_argument("--metrics", action="store_true", help="Show performance metrics")
    
    args = parser.parse_args()
    
    config = DownloadConfig(version=args.version)
    manager = DownloadManager(config)
    
    if args.download or args.force:
        success, _ = manager.download(force=args.force)
        if args.metrics:
            manager.print_metrics()
        
        if success and args.test:
            executable_path = manager.get_executable_path()
            if executable_path:
                wrapper = CloudflareSpeedTestWrapper(executable_path)
                results = wrapper.run_test_sync()
                print(f"\nTest Results:")
                for i, result in enumerate(results[:5], 1):
                    print(f"{i}. {result['ip']} - {result['latency']}ms - {result['download_speed']}MB/s - {result['region_code']}")


if __name__ == "__main__":
    main()
