# Linux System Performance And Stability Monitor

[![Python Version](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Linux System Performance And Stability Monitor

## architecture


## Build
```bash
git clone --recurse-submodules https://github.com/JiaoTuan/monitor.git
```
### ebpf tools build
```bash
apt install clang libelf1 libelf-dev zlib1g-dev
cd toole/bpf/
make
```
### usage
```bash
python3 ./lpm/cli.py --check=True --verbose=True
```