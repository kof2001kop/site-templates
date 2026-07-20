from __future__ import annotations
import ipaddress
import platform
import subprocess
import os
import datetime
import random
import base64
import csv

# ================= 差异化采样网段配置（与本地 6 网段严格一致版） =================
# 1. 实际热门网段（连通率极高、高占比）：无需过度扫描，每个网段轻量抽取 10 个做基础采样
warp_cidr_hot = [
    '188.114.96.0/24',
    '188.114.97.0/24',
    '188.114.98.0/24',
    '188.114.99.0/24'
]

# 2. 实际稀缺冷门网段（拦截严重、存活极低）：每个网段深度抽取 60 个，极限挖掘生存节点
warp_cidr_cold = [
    '162.159.192.0/24',
    '162.159.195.0/24'
]
# ======================================================================

script_directory = os.path.dirname(os.path.abspath(__file__))
ip_txt_path = os.path.join(script_directory, 'ip.txt')
result_path = os.path.join(script_directory, 'result.csv')
export_directory = os.path.join(script_directory, 'export')

def get_subnet_key(ip: str, granularity: str = "narrow") -> str | None:
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return None
    prefix = 24 if ip_obj.version == 4 else 48
    try:
        return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))
    except ValueError:
        return None

def sample_cidr_ips(cidr_list: list[str], ips_per_cidr: int) -> list:
    """通用子网IP随机采样辅助函数"""
    sampled_ips = []
    for cidr in cidr_list:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            hosts = list(network.hosts())
            if len(hosts) >= ips_per_cidr:
                sampled = random.sample(hosts, ips_per_cidr)
                sampled_ips.extend(sampled)
        except ValueError as e:
            print(f"Error parsing CIDR {cidr}: {e}")
    return sampled_ips

def create_ips():
    """
    [方案D-PRO-差异化采样（160 规模放大版）] 
    """
    hot_sampled = sample_cidr_ips(warp_cidr_hot, ips_per_cidr=10)
    cold_sampled = sample_cidr_ips(warp_cidr_cold, ips_per_cidr=60)
    
    all_sampled_ips = hot_sampled + cold_sampled

    # 写入 ip.txt 待扫描
    with open(ip_txt_path, 'w') as file:
        file.write('\n'.join(str(ip) for ip in all_sampled_ips))

if os.path.isfile(ip_txt_path):
    print("ip.txt exists.")
else:
    print('Creating ip.txt File...')
    create_ips()
    print('ip.txt File Created Successfully!')

def arch_suffix() -> str:
    machine = platform.machine().lower()
    if machine.startswith('i386') or machine.startswith('i686'):
        return '386'
    elif machine.startswith(('x86_64', 'amd64')):
        return 'amd64'
    elif machine.startswith(('armv8', 'arm64', 'aarch64')):
        return 'arm64'
    elif machine.startswith('s390x'):
        return 's390x'
    else:
        raise ValueError("Unsupported CPU architecture")

arch = arch_suffix()

print("Fetch warp program...")
url = f"https://gitlab.com/Misaka-blog/warp-script/-/raw/main/files/warp-yxip/warp-linux-{arch}"

# 下载对应架构的 warp binary
subprocess.run(["wget", url, "-O", "warp"])
os.chmod("warp", 0o755)

print(f"Scanning IPs via absolute path: {ip_txt_path}...")
process = subprocess.run(
    ["./warp", "-f", ip_txt_path, "-o", result_path],
    shell=False
)

if process.returncode != 0:
    print(f"Warning: Warp execution returned non-zero code: {process.returncode}")
else:
    print("Warp executed successfully.")

# ---【云端可用节点网段诊断工具】---
def print_result_diagnostics():
    if not os.path.exists(result_path):
        print("[诊断错误] 未找到 result.csv 扫描结果文件")
        return
    
    subnet_counts = {}
    total_successful = 0
    try:
        with open(result_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)  # 跳过表头
            for row in reader:
                if not row:
                    continue
                ipport = row[0].strip()
                ip, _ = ipport.split(":", 1) if ":" in ipport else (ipport, "")
                if ip:
                    total_successful += 1
                    subnet = get_subnet_key(ip)
                    if subnet:
                        subnet_counts[subnet] = subnet_counts.get(subnet, 0) + 1
                        
        print("\n" + "📊" + " [云端扫描诊断报告] " + "="*45)
        print(f" 本轮扫描出的【可用（连通）Endpoint】总数: {total_successful} 个")
        print(f" 成功可连通节点在 {len(warp_cidr_hot) + len(warp_cidr_cold)} 个网段中的物理分布统计:")
        for subnet in sorted(warp_cidr_hot + warp_cidr_cold):
            count = subnet_counts.get(subnet, 0)
            status_tag = "[活跃 ✓]" if count > 0 else "[无可用 ✗]"
            print(f"   - {subnet:<18} : {count:>3} 个可用 {status_tag}")
        print("=" * 65 + "\n")
    except Exception as e:
        print(f"[诊断失败] 解析 result.csv 异常: {e}")

# 运行诊断打印
print_result_diagnostics()
# --------------------------------------------

def warp_ip() -> str:
    config_prefixes = ''  
    with open(result_path, 'r') as csv_file:
        next(csv_file)
        for line in csv_file:
            ip = line.split(',')[0]
            config_prefixes += f'{ip}\n'
    return config_prefixes

configs = warp_ip()

# 将原本明文的 IP 结果转换成 Base64 乱码
encoded_configs = base64.b64encode(configs.encode('utf-8')).decode('utf-8')

os.makedirs(export_directory, exist_ok=True)
# 伪装输出至普通网页配置文件 manifest.json
export_file_path = os.path.join(export_directory, 'manifest.json')
with open(export_file_path, 'w') as op:
    op.write(encoded_configs)

# 清理所有本地残留文件
if os.path.exists(ip_txt_path):
    os.remove(ip_txt_path)
if os.path.exists(result_path):
    os.remove(result_path)
if os.path.exists("warp"):
    os.remove("warp")
