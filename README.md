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

# Cloudflare 优选 IP 库 (物理地理位置版)

本项目基于 [DustinWin/BestCF](https://github.com/DustinWin/BestCF) 进行二次开发，旨在为用户提供**经过物理地理位置校准**的 Cloudflare 优选 IP 和域名。与传统的 Anycast 探测不同，本项目通过 GeoIP 数据库识别 IP 的真实注册地，解决了在云端运行脚本时所有 IP 都被误分类为美国（US）的问题。

## 🌟 项目特色

* **物理位置分类**：通过 ip-api 批量查询，精准识别 IP 真实的归属地（HK, SG, JP, US 等），而非 GitHub 服务器所在的 Anycast 路由地。
* **全汇总订阅**：提供 `all-countries-ip.txt`，包含所有优选 IP 并自动标记国家码，格式为 `IP#国家码`。
* **运营商精选**：保留了原项目对中国移动 (CMCC)、中国联通 (CUCC) 和中国电信 (CTCC) 的针对性优选。
* **全自动化更新**：利用 GitHub Actions 每 12 小时自动抓取数据、探测地理位置并发布更新。

---

## 📂 数据结构说明

所有优选结果均存储在 [bestcf 分支](https://www.google.com/search?q=https://github.com/Abernnano/BestCF/tree/bestcf) 中，结构如下：

```text
├── all-countries-ip.txt      # 全量汇总文件 (格式: IP#国家码)
├── bestcf-domain.txt         # 优选域名汇总
├── HK/                       # 香港优选 IP 目录
│   ├── cmcc-ip.txt
│   ├── ctcc-ip.txt
│   └── cucc-ip.txt
├── SG/                       # 新加坡优选 IP 目录
│   └── ...
├── JP/                       # 日本优选 IP 目录
│   └── ...
└── (其他国家码目录...)

```

---

## 🔗 快速调用链接

为了保证访问速度，推荐使用 **jsDelivr CDN** 或 **GitHub Raw** 链接。请将 `[用户名]` 替换为 `Abernnano`。

### 1. 全球全量汇总 (推荐)

| 文件名 | GitHub Raw 链接 |
| --- | --- |
| **全国家汇总** | `https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/all-countries-ip.txt` |

### 2. 按国家分类 (精选)

| 区域 | 移动 (CMCC) | 联通 (CUCC) | 电信 (CTCC) |
| --- | --- | --- | --- |
| **香港 (HK)** | [点击访问](https://www.google.com/search?q=https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/HK/cmcc-ip.txt) | [点击访问](https://www.google.com/search?q=https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/HK/cucc-ip.txt) | [点击访问](https://www.google.com/search?q=https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/HK/ctcc-ip.txt) |
| **日本 (JP)** | [点击访问](https://www.google.com/search?q=https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/JP/cmcc-ip.txt) | [点击访问](https://www.google.com/search?q=https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/JP/cucc-ip.txt) | [点击访问](https://www.google.com/search?q=https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/JP/ctcc-ip.txt) |
| **新加坡 (SG)** | [点击访问](https://www.google.com/search?q=https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/SG/cmcc-ip.txt) | [点击访问](https://www.google.com/search?q=https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/SG/cucc-ip.txt) | [点击访问](https://www.google.com/search?q=https://raw.githubusercontent.com/Abernnano/BestCF/bestcf/SG/ctcc-ip.txt) |

> **提示**：若要在 Clash 或 sing-box 中使用，直接引用上述 Raw 链接作为 `proxy-providers` 的源即可。

---

## 🛠️ 如何自建

1. **Fork 本仓库**。
2. 前往 `Settings` -> `Actions` -> `General`，确保 **Workflow permissions** 设置为 `Read and write permissions`。
3. 点击 `Actions` 选项卡，手动启用并运行 **Generate bestcf** 工作流。
4. 脚本会自动在你的仓库创建 `bestcf` 分支并存储结果。

---

## 🙏 鸣谢

* [DustinWin/BestCF](https://github.com/DustinWin/BestCF) (原项目基础)
* [CMLiussss](https://www.google.com/search?q=https://github.com/CMLiussss) (IP 源提供)
* [ip-api.com](https://ip-api.com/) (地理位置数据支持)

---

> **免责声明**：本项目仅供学习交流使用，不提供任何形式的代理服务。所有 IP 数据均来自公开互联网，不对 IP 的可用性或安全性负责。
