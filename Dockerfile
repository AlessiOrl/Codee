FROM python:3.11
WORKDIR /codee
COPY ./requirements.txt /codee/requirements.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir --upgrade -r /codee/requirements.txt
RUN apt-get -y update
RUN apt-get install ffmpeg libsm6 libxext6  -y
COPY ./app /codee/app
COPY ./data /codee/data
CMD ["python", "app/main.py"]
