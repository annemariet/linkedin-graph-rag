# Fitbit Analysis development environment (minimal)
FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

# Install system dependencies
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        build-essential \
        curl \
        git \
        wget \
        software-properties-common \
        ca-certificates \
        vim \
        nano \
        htop \
        tree \
        jq \
        openssh-client \
    && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install Python 3.11+ and uv
RUN add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get -y install --no-install-recommends \
        python3.11 \
        python3.11-dev \
        python3.11-venv \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && mv /root/.local/bin/uvx /usr/local/bin/uvx

# Install minimal Python development tools using uv
RUN uv tool install black \
    && uv tool install jupyter \
    && uv tool install ipython

# Set up development user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Create the user if it doesn't exist
RUN if ! id -u $USERNAME > /dev/null 2>&1; then \
        groupadd --gid $USER_GID $USERNAME \
        && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
        && apt-get update \
        && apt-get install -y sudo \
        && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
        && chmod 0440 /etc/sudoers.d/$USERNAME; \
    fi

# Set up workspace directory
RUN mkdir -p /workspace && chown $USERNAME:$USERNAME /workspace

# Switch to development user
USER $USERNAME

# Set working directory
WORKDIR /workspace

# Configure git for the development user
RUN git config --global init.defaultBranch main \
    && git config --global core.autocrlf input \
    && git config --global pull.rebase false \
    && git config --global core.editor "code --wait"

# Set up shell environment
RUN echo 'export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"' >> ~/.bashrc \
    && echo 'export PYTHONPATH="/workspace:$PYTHONPATH"' >> ~/.bashrc \
    && echo 'alias ll="ls -la"' >> ~/.bashrc \
    && echo 'alias black="python -m black"' >> ~/.bashrc \
    && echo 'alias pip="uv pip"' >> ~/.bashrc \
    && echo 'alias jupyter="jupyter"' >> ~/.bashrc

# Default command
CMD ["sleep", "infinity"]