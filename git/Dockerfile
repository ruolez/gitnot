FROM debian:trixie-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git fcgiwrap openssh-server python3 tini ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 1000 -m -d /home/git -s /bin/sh git \
    && passwd -d git >/dev/null \
    && mkdir -p /data/repos /etc/mygit /run/sshd \
    && chown git:git /data/repos \
    && rm -f /etc/ssh/ssh_host_*

COPY gitconfig /etc/gitconfig
COPY hooks/ /opt/mygit/hooks/
COPY bin/ /usr/local/bin/
COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /opt/mygit/hooks/pre-receive /opt/mygit/hooks/post-receive /entrypoint.sh \
    && find /usr/local/bin -type f -exec chmod 755 {} +

EXPOSE 9000 22
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
