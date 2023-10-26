FROM python:3-alpine

WORKDIR /usr/src/app
RUN pip install --no-cache-dir qlient==1.0.0

RUN apk add --no-cache openldap-clients

COPY lldap_init.py .

CMD [ "python", "/usr/src/app/lldap_init.py" ]
