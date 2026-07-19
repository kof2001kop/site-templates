import ipaddress
import platform
import subprocess
import os
import datetime
import random
import base64

warp_cidr = [
    '162.159.192.0/24',
    '162.159.193.0/24',
    '162.159.195.0/24',
    '162.159.204.0/24',
    '188.114.96.0/24',
    '188.114.97.0/24',
    '188.114.98.0/24',
    '188.114.99.0/24'
]

script_directory = os.path.dirname(__file__)
ip_txt_path = os.path.join(script_directory, 'ip.txt')
result_path = os.path.join(script_directory, 'result.csv')
export_directory = os.path.join(script_directory, 'export')

def create_ips():
    ips_per_cidr = 3
    all_sampled_ips = []

    for cidr in warp_cidr:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            hosts = list(network.hosts())
            if len(hosts) >= ips_per_cidr:
                sampled = random.sample(hosts, ips_per_cidr)
                all_sampled_ips.extend(sampled)
        except ValueError as e:
            print(f"Error parsing CIDR {cidr}: {e}")

    with open(ip_txt_path, 'w') as file:
        file.write('\n'.join(str(ip) for ip in all_sampled_ips))

if os.path.isfile(ip_txt_path):
    print("ip.txt exists.")
else:
    print('Creating ip.txt File.')
    create_ips()
    print('ip.txt File Created Successfully!')

def arch_suffix():
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

subprocess.run(["wget", url, "-O", "warp"])
os.chmod("warp", 0o755)

print("Scanning ips...")

process = subprocess.run(
    ["./warp"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    shell=False
)

if process.returncode != 0:
    print("Error: Warp execution failed.")
else:
    print("Warp executed successfully.")

def warp_ip():
    creation_time = os.path.getctime(result_path)
    formatted_time = datetime.datetime.fromtimestamp(creation_time).strftime("%Y-%m-%d %H:%M:%S")
    config_prefixes = ''  
    with open(result_path, 'r') as csv_file:
        next(csv_file)
        for line in csv_file:
            ip = line.split(',')[0]
            config_prefixes += f'{ip}\n'
    return config_prefixes, formatted_time

configs = warp_ip()[0]

encoded_configs = base64.b64encode(configs.encode('utf-8')).decode('utf-8')

os.makedirs(export_directory, exist_ok=True)
export_file_path = os.path.join(export_directory, 'manifest.json')
with open(export_file_path, 'w') as op:
    op.write(encoded_configs)

if os.path.exists(ip_txt_path):
    os.remove(ip_txt_path)
if os.path.exists(result_path):
    os.remove(result_path)
if os.path.exists("warp"):
    os.remove("warp")
