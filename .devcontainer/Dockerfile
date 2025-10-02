# Multi-project development environment
FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

# Install system dependencies
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        build-essential \
        curl \
        git \
        wget \
        unzip \
        zip \
        software-properties-common \
        ca-certificates \
        gnupg \
        lsb-release \
        postgresql-client \
        redis-tools \
        vim \
        nano \
        htop \
        tree \
        jq \
        make \
        openssh-client \
        rsync \
    && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install Python 3.12+ and uv
RUN add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get -y install --no-install-recommends \
        python3.12 \
        python3.12-dev \
        python3.12-venv \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && mv /root/.local/bin/uvx /usr/local/bin/uvx

# Install Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Install Docker CLI
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get -y install --no-install-recommends docker-ce-cli docker-compose-plugin

# Install common Python development tools using uv
RUN uv tool install black \
    && uv tool install flake8 \
    && uv tool install mypy \
    && uv tool install pytest \
    && uv tool install pre-commit \
    && uv tool install pipenv \
    && uv tool install bandit \
    && uv tool install safety \
    && uv tool install isort \
    && uv tool install autopep8

# Install common Node.js development tools
RUN npm install -g \
    eslint \
    prettier \
    typescript \
    ts-node \
    nodemon \
    @types/node \
    yarn \
    pnpm \
    jest \
    vitest \
    @typescript-eslint/parser \
    @typescript-eslint/eslint-plugin

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
RUN mkdir -p /workspaces && chown $USERNAME:$USERNAME /workspaces

# Switch to development user
USER $USERNAME

# Set working directory
WORKDIR /workspaces

# Configure git for the development user
RUN git config --global init.defaultBranch main \
    && git config --global core.autocrlf input \
    && git config --global pull.rebase false \
    && git config --global core.editor "code --wait" \
    && git config --global diff.tool "code --wait --diff" \
    && git config --global merge.tool "code --wait"

# Note: Project-specific dependencies should be managed with uv per-project

# Set up shell environment
RUN echo 'export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"' >> ~/.bashrc \
    && echo 'export PYTHONPATH="/workspaces:$PYTHONPATH"' >> ~/.bashrc \
    && echo 'alias ll="ls -la"' >> ~/.bashrc \
    && echo 'alias la="ls -A"' >> ~/.bashrc \
    && echo 'alias l="ls -CF"' >> ~/.bashrc \
    && echo 'alias grep="grep --color=auto"' >> ~/.bashrc \
    && echo 'alias fgrep="fgrep --color=auto"' >> ~/.bashrc \
    && echo 'alias egrep="egrep --color=auto"' >> ~/.bashrc \
    && echo 'alias projects="cd /workspaces && find projects -maxdepth 1 -type d | sort"' >> ~/.bashrc \
    && echo 'alias pytest="python -m pytest"' >> ~/.bashrc \
    && echo 'alias black="python -m black"' >> ~/.bashrc \
    && echo 'alias mypy="python -m mypy"' >> ~/.bashrc \
    && echo 'alias pip="uv pip"' >> ~/.bashrc

# Default command
CMD ["sleep", "infinity"]