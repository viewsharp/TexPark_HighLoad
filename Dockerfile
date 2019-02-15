FROM pypy:3
MAINTAINER Vladimir Atamanov

ADD httpserver.py /opt/httpserver/httpserver.py

EXPOSE 80

WORKDIR /opt/httpserver
ENTRYPOINT pypy3 httpserver.py