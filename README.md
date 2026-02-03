# Cloudflare 优选域名和 IP
## 数据源
forked from DustinWin/BestCF

1. 每 12 小时（UTC+0）自动构建
2. **bestcf-domain.txt** 源采用 [CMLiussss（优选域名）](https://cf.090227.xyz)、[VPS789（优选 CNAME 域名）](https://vps789.com/cfip/?remarks=domain) 和[微测网（CloudFlare 优选 Cname 域名）](https://www.wetest.vip/page/cloudflare/cname.html)组合
3. **cmcc-ip.txt** 源采用 [CMLiussss（移动优选 IP）](https://cf.090227.xyz/cmcc)（IPv4 & IPv6）、[VPS789（移动优选 IP）](https://vps789.com/cfip/)（IPv4）、[CloudFlareYes（移动优选 IP）](https://stock.hostmonit.com/CloudFlareYes)（IPv4 & IPv6）和[微测网（移动优选 IP）](https://www.wetest.vip/page/cloudflare/address_v4.html)（IPv4 & IPv6）组合
4. **cucc-ip.txt** 源采用 [CMLiussss（联通优选 IP）](https://cf.090227.xyz/cu)（IPv4）、[VPS789（联通优选 IP）](https://vps789.com/cfip/)（IPv4）、[CloudFlareYes（联通优选 IP）](https://stock.hostmonit.com/CloudFlareYes)（IPv4 & IPv6）和[微测网（联通优选 IP）](https://www.wetest.vip/page/cloudflare/address_v4.html)（IPv4 & IPv6）组合
5. **ctcc-ip.txt** 源采用 [CMLiussss（电信优选 IP）](https://cf.090227.xyz/ct)（IPv4）、[VPS789（电信优选 IP）](https://vps789.com/cfip/)（IPv4）、[CloudFlareYes（电信优选 IP）](https://stock.hostmonit.com/CloudFlareYes)（IPv4 & IPv6）和[微测网（电信优选 IP）](https://www.wetest.vip/page/cloudflare/address_v4.html)（IPv4 & IPv6）组合
6. **bestcf-ip.txt** 源采用 [VPS789（CF 优选 IP）](https://vps789.com/cfip/)（IPv4）、[CloudflareSpeedTest（Cloudflare 优选 IP 测速数据）](https://ip.164746.xyz)（IPv4）、[IPDB（CF 优选官方 IP 服务）](https://ipdb.030101.xyz/bestcfv4/)（IPv4 & IPv6）组合
7. **proxy-ip.txt**（反代 IP）[IPDB（CF 优选官方反代 IP 服务）](https://ipdb.030101.xyz/bestproxy/)（IPv4）组合

---

# Cloudflare 优选 IP 库 (本地路由优化版)

本项目是基于 [DustinWin/BestCF](https://github.com/DustinWin/BestCF) 的二次开发版本。通过部署在 **英国 (GB)** 的自托管运行器进行实时探测，确保生成的分类结果完全符合真实的本地网络路由。

### 🌟 核心突破：解决 Anycast 误判

传统的 GitHub Actions 运行在美区服务器，由于 Cloudflare 的 Anycast 技术，会导致大部分 IP 被识别为 `US`。本项目通过本地运行器访问 `cdn-cgi/trace` 接口，能够识别出流量实际落地的节点（如 `GB`, `HK`, `JP`），为特定地区用户提供最精准的优选结果。

### 📂 分支与目录说明

* **`main` 分支**：存放自动化脚本与过滤逻辑。
* **`bestcf` 分支**：存放优选结果。
* **`all-countries-ip.txt`**：全球 IP 汇总，格式为 `IP#国家码`。
* **`GB/`**, **`HK/`**, **`SG/`**...：按实际路由国家分类的运营商优选列表。
* **`proxy-ip.txt`**：原始反代 IP，不参与国家分类以保持纯净。



### 🔗 快速订阅链接 (以英国区域为例)

| 节点类型 | GitHub Raw 链接 |
| --- | --- |
| **全国家汇总 (推荐)** | `https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/all-countries-ip.txt` |
| **移动-英国 (GB)** | `https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/GB/cmcc-ip.txt` |
| **联通-英国 (GB)** | `https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/GB/cucc-ip.txt` |
| **电信-英国 (GB)** | `https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/GB/ctcc-ip.txt` |

---

## 第二部分：完整的本地自托管运行器教程

如果你需要在其他机器上复现，或需要重新配置，请参考以下指南。

### 1. 环境准备 (Windows)

* **Python**: 安装 Python 3.10+，并确保已勾选 `Add Python to PATH`。
* **Git**: 安装 Git for Windows，用于将结果推送至仓库。
* **依赖库**: 打开 PowerShell 执行：
```powershell
pip install requests

```



### 2. 部署 Runner (自托管运行器)

1. **项目设置**: 进入 GitHub 仓库 `Settings` -> `Actions` -> `Runners` -> `New self-hosted runner`。
2. **下载与解压**: 在 `E:\actions-runner` (或你自定义的路径) 执行 GitHub 提供的下载与解压命令。
3. **关键配置**: 执行 `./config.cmd`。
* **Runner Group**: 直接按 **Enter**。
* **Runner Name**: 自定义（如 `UK-Home-Server`）。
* **Labels**: 直接按 **Enter**，确保拥有 `self-hosted` 标签。


4. **运行**: 执行 `./run.cmd`。

### 3. 修改 Workflow 配置文件

确保项目中的 `.github/workflows/build.yml` 的 `runs-on` 字段已设为 `self-hosted`：

```yaml
jobs:
  build:
    runs-on: self-hosted # 关键：让任务在你的英国本地机器运行
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      # 后续执行 curl 抓取与 python filter.py 逻辑

```

### 4. 长期稳定运行方案

为了避免关闭 PowerShell 窗口导致运行器失效，建议将其安装为 Windows 服务：

1. 在 `actions-runner` 文件夹下，以管理员权限打开 PowerShell。
2. 停止当前运行（Ctrl+C）。
3. 执行：`./svc.sh install`。
4. 执行：`./svc.sh start`。
现在，运行器将在后台静默运行，即便重启电脑也会自动启动。

---

## 第三部分：核心逻辑维护 (filter.py)

你的 `filter.py` 脚本目前具备以下高级逻辑：

1. **实时探测**: 优先使用本地网络访问 `trace` 接口，获取最真实的 `loc` 国家码。
2. **严格排除**: 识别并跳过 `proxy-ip.txt`，确保反代 IP 不被错误地移入国家目录。
3. **汇总增强**: 自动生成 `all-countries-ip.txt` 并处理 IPv6 格式。
