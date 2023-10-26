FROM python:3

WORKDIR /usr/src/app
RUN pip install --no-cache-dir qlient

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt install -y ldap-utils && rm -rf /var/lib/apt/lists/*

COPY lldap_init.py .

CMD [ "python", "/usr/src/app/lldap_init.py" ]
