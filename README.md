# Cloudflare 优选全球 IP 自动化系统

本项目基于DustinWin/BestCF项目，通过 GitHub Actions 自托管运行器（Windows），利用本地宽带环境实现对 Cloudflare 边缘节点的实时抓取、全球数据中心（Colo）识别及分类标注。

## 🌟 项目特性

* **本地化探测**：利用自托管运行器绕过 GitHub 官方服务器的路由黑盒，获取最真实的本地连接结果。
* **全球机房识别**：通过解析 `colo` 代码识别 IP 实际落地的数据中心（如 HKG、SIN、LAX），而非客户端位置。
* **全自动分流**：适配 Windows 环境下的代理分流逻辑，确保代码拉取走代理，探测过程走直连。
* **多线路支持**：自动分类 移动 (CMCC)、联通 (CUCC)、电信 (CTCC) 及全网优选 IP。

---

## 🛠️ 第一部分：本地环境配置 (Windows)

在你的自托管运行器机器上，需完成以下基础设置：

### 1. Git 工具链与环境变量

安装 Git for Windows（推荐路径 `D:\APP\Git`），并将以下路径手动添加到系统的 **Path** 环境变量中：

* `D:\APP\Git\bin`
* `D:\APP\Git\usr\bin`（此路径包含 `grep`, `awk` 等关键 Linux 工具）

> **注意**：配置完成后必须关闭并重新启动 `./run.cmd` 窗口，环境变量才能生效。

### 2. 安装 `jq` 工具

1. 下载 [jq-windows-amd64.exe](https://www.google.com/search?q=https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-windows-amd64.exe) 并重命名为 `jq.exe`。
2. 移动至 `D:\APP\Git\usr\bin` 目录下。

### 3. Python 环境

1. 确保本地已安装 Python 3.x。
2. 执行依赖安装：`pip install requests`。

---

## 🌐 第二部分：网络分流逻辑 (Clash Verge)

为了让运行器既能通过代理拉取代码，又能通过直连探测真实路由，需在 **Clash Verge** 的 **全局扩展覆盖配置 (Merge)** 中添加以下规则：

```yaml
ipv6: true  # 必须为 true，否则 Clash 不会处理 IPv6 流量

profile:
  store-selected: true

prepend-rules:
  # 1. 强制 Cloudflare 探测及优选 IP 走直连 (确保探测出本地真实路由)
  - DOMAIN,cp.cloudflare.com,DIRECT
  - IP-CIDR,1.1.1.1/32,DIRECT
  - IP-CIDR,1.0.0.1/32,DIRECT
  # 如果你有特定的优选 IP 段，在此处添加，例如：
  # - IP-CIDR,104.16.0.0/12,DIRECT

  # 2. GitHub 相关流量 (合并重复项，确保 Runner、下载及认证正常)
  - DOMAIN-SUFFIX,github.com,Proxy
  - DOMAIN-SUFFIX,githubusercontent.com,Proxy
  - DOMAIN-SUFFIX,github.io,Proxy
  - DOMAIN-SUFFIX,githubapp.com,Proxy
  - DOMAIN-SUFFIX,ghcr.io,Proxy
  - DOMAIN-SUFFIX,pkg.github.com,Proxy
  - DOMAIN,objects.githubusercontent.com,Proxy
  - DOMAIN,codeload.github.com,Proxy
  - DOMAIN-SUFFIX,github-production-release-asset-2e65be.s3.amazonaws.com,Proxy
  - DOMAIN-KEYWORD,github,Proxy

  # 3. Microsoft 身份验证相关 (GitHub 登录/凭据管理器可能使用)
  - DOMAIN-SUFFIX,microsoft.com,Proxy
  - DOMAIN-SUFFIX,live.com,Proxy
  - DOMAIN-SUFFIX,msauth.net,Proxy

```

---

## 🚀 第三部分：线上配置与自动化流程

### 1. 工作流配置 (`.github/workflows/build.yml`)

在工作流中，需特别注意 Windows 环境下的命令兼容性：

* **强制 Bash 环境**：所有包含 `curl`, `awk` 等命令的步骤必须指定 `shell: bash`，以避开 PowerShell 的别名冲突。
* **SSL 豁免**：所有 `curl` 请求需携带 `--ssl-no-revoke` 参数，解决 Windows 下证书吊销服务器无法连接导致的报错。
* **路径隔离**：使用 `/usr/bin/sort` 明确调用 Linux 版排序工具，避免与 Windows 系统自带的 `sort.exe` 冲突。

### 2. 探测与分类逻辑 (`filter.py`)

脚本执行以下核心操作：

1. **排除特定文件**：严格排除 `proxy-ip.txt`，仅对指定的优选列表进行分类。
2. **全球机房映射**：通过 `COLO_MAP` 将三字码（如 `HKG`）映射为国家码（如 `HK`）。
3. **格式化输出**：在 `#` 符号后标注国家码，格式为 `IP#国家码_来源标签`。
4. **编码保护**：强制使用 `UTF-8` 输出，防止 Windows 控制台因 GBK 编码无法处理 Emoji 或特殊字符而崩溃。

---

## 📝 第四部分：维护建议

### 常见问题排查 (FAQ)

* **识别结果全是 CN？** 请检查 Clash 规则中 `cp.cloudflare.com` 是否真的走了 `DIRECT`。
* **脚本报错 `jq: command not found`？** 确认 `jq.exe` 已放入 `usr/bin` 且已彻底重启运行器进程。
* **Git 推送失败？** 请确保 `GITHUB_TOKEN` 具有 `contents: write` 权限，或者在本地配置 SSH 密钥。

---


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
