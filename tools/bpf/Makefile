# lpm/ebpf/Makefile

# 基础配置
LIBBPF_BOOTSTRAP := $(abspath ../../libbpf-bootstrap)
OUTPUT := $(abspath .output)
CLANG ?= clang

# 工具和库路径
LIBBPF_SRC := $(LIBBPF_BOOTSTRAP)/libbpf/src
BPFTOOL_SRC := $(LIBBPF_BOOTSTRAP)/bpftool/src
LIBBPF_OBJ := $(OUTPUT)/libbpf.a
BPFTOOL ?= $(shell which bpftool)
ARCH := $(shell uname -m | sed 's/x86_64/x86/' | sed 's/arm.*/arm/' | sed 's/aarch64/arm64/')
VMLINUX := $(LIBBPF_BOOTSTRAP)/vmlinux.h/include/$(ARCH)/vmlinux.h

# 包含路径
INCLUDES := -I$(OUTPUT) -I$(LIBBPF_BOOTSTRAP)/libbpf/include/uapi -I$(dir $(VMLINUX))
CFLAGS := -g -Wall

# 静态编译配置
STATIC_FLAGS := -static
LDFLAGS += $(STATIC_FLAGS)
LDLIBS := -lelf -lz -lzstd  # 添加zstd

# 程序配置
APPS = dmabuf

# 确保目录存在
$(shell mkdir -p $(OUTPUT))

# 构建规则
all: $(APPS)

$(OUTPUT)/%.bpf.o: %.bpf.c $(LIBBPF_OBJ) | $(OUTPUT)
	$(CLANG) -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH) \
		$(INCLUDES) -c $< -o $@

$(OUTPUT)/%.skel.h: $(OUTPUT)/%.bpf.o | $(OUTPUT)
	$(BPFTOOL) gen skeleton $< > $@

$(OUTPUT)/%.o: %.c $(OUTPUT)/%.skel.h | $(OUTPUT)
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

$(LIBBPF_OBJ): | $(OUTPUT)
	$(MAKE) -C $(LIBBPF_SRC) BUILD_STATIC_ONLY=1 \
		OBJDIR=$(OUTPUT)/libbpf DESTDIR=$(OUTPUT) \
		INCLUDEDIR= LIBDIR= UAPIDIR= install

$(APPS): %: $(OUTPUT)/%.o $(LIBBPF_OBJ)
	$(CC) $(CFLAGS) $(STATIC_FLAGS) $^ $(LDLIBS) -o $@

clean:
	rm -rf $(OUTPUT) $(APPS)

.PHONY: all clean