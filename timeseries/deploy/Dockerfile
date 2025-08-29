FROM python:3.10

ARG ENVIRONMENT
ENV ENVIRONMENT="${ENVIRONMENT}"

COPY deploy/requirements /code/deploy/requirements
COPY deploy/logging /code/deploy/logging

WORKDIR /code

RUN apt-get update && apt-get install -y libgdal-dev

RUN mkdir /shared && pip install -r deploy/requirements/base.txt -r deploy/requirements/${ENVIRONMENT}.txt

COPY app metadata.yml /code/

CMD ["uvicorn", "--reload", "--host", "0.0.0.0", "app.main:app"]
