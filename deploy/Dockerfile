FROM python:3.10

ARG ENVIRONMENT
ENV ENVIRONMENT="${ENVIRONMENT}"

RUN apt-get update && apt-get install -y libgdal-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /code

RUN pip install --no-cache-dir --upgrade pip "setuptools<70.0.0" wheel "Cython<3.0.0" "numpy<1.24" # probably just need to update the stack, but for now...

COPY deploy/requirements /code/requirements

RUN mkdir /shared && \
    pip install --no-cache-dir --no-build-isolation \
    -r requirements/base.txt -r requirements/${ENVIRONMENT}.txt

COPY deploy/logging/${ENVIRONMENT}.yml /code/config/logging.yml
COPY deploy/settings/${ENVIRONMENT}.yml /code/config/app_settings.yml

COPY timeseries/app /code/app
COPY timeseries/metadata.yml /code/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--reload"]
