FROM redis:latest

RUN mkdir /etc/redis
RUN mkdir /var/log/redis

COPY configs/sentinel.conf /etc/redis/sentinel.conf

RUN chown -R redis:redis /etc/redis
RUN chown -R redis:redis /var/log/redis