FROM python:3-alpine

ARG USER=lldap_init

RUN apk add --no-cache --no-progress --quiet openldap-clients
RUN pip install --disable-pip-version-check --root-user-action=ignore --no-cache-dir --quiet qlient==1.0.0

RUN adduser -D -H $USER
USER $USER

WORKDIR /usr/src/app
COPY lldap_init.py .

CMD [ "python", "/usr/src/app/lldap_init.py" ]
