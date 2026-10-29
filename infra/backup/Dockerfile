# The backup container (TRD §16.4; W20-6, W20-7). Built from infra/ (see compose.backup.yml).
# Built on the Mongo image so mongodump, mongorestore and mongosh are the same version as the
# server; adds rclone (copies to the backup host), age (encrypts) and Python for the retention
# rule. Runs as a user of its own and holds no key that can decrypt a backup.
FROM mongo:8.0.34

RUN apt-get update \
 && apt-get install -y --no-install-recommends rclone age python3-minimal ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --system --uid 10002 --user-group --home-dir /nonexistent --shell /usr/sbin/nologin mmsbackup \
 && mkdir -p /backups /textfile /state \
 && chown mmsbackup:mmsbackup /backups /textfile /state

COPY backup/backup.sh backup/loop.sh backup/retention.py /opt/backup/
RUN chmod 0755 /opt/backup/backup.sh /opt/backup/loop.sh

# mongosh wants a home folder to write to
ENV HOME=/tmp RCLONE_LOG_LEVEL=ERROR
USER mmsbackup
WORKDIR /opt/backup
ENTRYPOINT ["/opt/backup/loop.sh"]
