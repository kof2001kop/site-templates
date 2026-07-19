from __future__ import annotations
import ipaddress
import platform
import subprocess
import os
import datetime
import random
import base64
import tarfile

# ================= 差异化采样网段配置 =================
# 1. 热门网段（连通率高、拥挤、GFW特征重点扫描区）：每个网段仅抽取 10 个
warp_cidr_hot = [
    '162.159.192.0/24',
    '162.159.193.0/24',
    '162.159.195.0/24',
    '162.159.204.0/24'
]

# 2. 冷门网段（连通率低、空闲、有CDN网页流量作为天然保护伞）：每个网段深度抽取 30 个以寻找隐蔽节点
warp_cidr_cold = [
    '188.114.96.0/24',
    '188.114.97.0/24',
    '188.114.98.0/24',
    '188.114.99.0/24'
]
# ======================================================

script_directory = os.path.dirname(os.path.abspath(__file__))
ip_txt_path = os.path.join(script_directory, 'ip.txt')
result_path = os.path.join(script_directory, 'result.csv')
export_directory = os.path.join(script_directory, 'export')

def sample_cidr_ips(cidr_list: list[str], ips_per_cidr: int) -> list:
    """通用子网IP随机采样辅助函数"""
    sampled_ips = []
    for cidr in cidr_list:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            # 排除网络地址与广播地址，仅获取可用主机IP列表
            hosts = list(network.hosts())
            if len(hosts) >= ips_per_cidr:
                # 随机采样，避免产生顺序或连续规律
                sampled = random.sample(hosts, ips_per_cidr)
                sampled_ips.extend(sampled)
        except ValueError as e:
            print(f"Error parsing CIDR {cidr}: {e}")
    return sampled_ips

def create_ips():
    """
    [方案D-PRO-差异化采样（160 规模放大版）] 
    1. 热门网段（4个）：每个网段随机抽取 10 个（共 40 个），节省测试负荷。
    2. 冷门网段（4个）：每个网段深度抽取 30 个（共 120 个，大幅增加大海捞针概率）。
    总共生成 160 个高物理层多样性的候选 IP 写入 ip.txt。
    """
    hot_sampled = sample_cidr_ips(warp_cidr_hot, ips_per_cidr=10)
    cold_sampled = sample_cidr_ips(warp_cidr_cold, ips_per_cidr=30)
    
    all_sampled_ips = hot_sampled + cold_sampled

    # 写入 ip.txt 待扫描
    with open(ip_txt_path, 'w') as file:
        file.write('\n'.join(str(ip) for ip in all_sampled_ips))

if os.path.isfile(ip_txt_path):
    print("ip.txt exists.")
else:
    print('Creating ip.txt File.')
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

print("Fetch CloudflareWarpSpeedTest program...")
# 使用指定的正确下载地址格式
version = "v1.5.15"
url = f"https://github.com/puzige/CloudflareWarpSpeedTest/releases/download/{version}/CloudflareWarpSpeedTest-{version}-linux-{arch}.tar.gz"
tar_path = os.path.join(script_directory, 'warp.tar.gz')

# 下载 tar.gz 压缩包
subprocess.run(["wget", url, "-O", tar_path], check=True)

# 解压压缩包
with tarfile.open(tar_path) as tar:
    tar.extractall(path=script_directory)

# 赋予执行权限
warp_bin_path = os.path.join(script_directory, 'CloudflareWarpSpeedTest')
os.chmod(warp_bin_path, 0o755)

print("Scanning ips...")
# 【核心参数说明】：
# -f ip.txt : 强制读取你生成的 160 个 IP 列表
# -dd       : 禁用下载测速，仅测 WireGuard 握手连通性 (大幅节省时间)
# -o result.csv : 输出结果到 result.csv
process = subprocess.run(
    [warp_bin_path, "-f", ip_txt_path, "-dd", "-o", result_path],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    shell=False
)

if process.returncode != 0:
    print("Error: CloudflareWarpSpeedTest execution failed.")
else:
    print("CloudflareWarpSpeedTest executed successfully.")

def warp_ip() -> tuple[str, str]:
    creation_time = os.path.getctime(result_path)
    formatted_time = datetime.datetime.fromtimestamp(creation_time).strftime("%Y-%m-%d %H:%M:%S")
    config_prefixes = ''  
    with open(result_path, 'r') as csv_file:
        next(csv_file)  # 跳过首行表头
        for line in csv_file:
            ip = line.split(',')[0]
            config_prefixes += f'{ip}\n'
    return config_prefixes, formatted_time

configs = warp_ip()[0]

# 【加密核心】：将原本明文的 IP 结果转换成 Base64 乱码，防止防火墙或 GitHub 爬虫提取 IP 特征
encoded_configs = base64.b64encode(configs.encode('utf-8')).decode('utf-8')

os.makedirs(export_directory, exist_ok=True)
# 伪装输出至普通网页配置文件 manifest.json
export_file_path = os.path.join(export_directory, 'manifest.json')
with open(export_file_path, 'w') as op:
    op.write(encoded_configs)

# 清理所有本地残留文件，保证云端执行完后不留下可执行文件或明文结果
if os.path.exists(ip_txt_path):
    os.remove(ip_txt_path)
if os.path.exists(result_path):
    os.remove(result_path)
if os.path.exists(warp_bin_path):
    os.remove(warp_bin_path)
if os.path.exists(tar_path):
    os.remove(tar_path)
