FROM wuabit/snips-nlu
LABEL maintainer="Odiaosen mariatony.ejale@gmail.com"

# Mountpoint for configuration
VOLUME /config

RUN apt-get update \
  && apt-get upgrade -y \
  && apt-get install bash \
  && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy app into image
WORKDIR /usr/app
COPY . .

# Build-time metadata as defined at http://label-schema.org
ARG BUILD_DATE
ARG SNIPS_VERSION=0.20.2

LABEL org.label-schema.build-date=$BUILD_DATE \
      org.label-schema.name="Snips NLU App" \
      org.label-schema.description="This docker image runs the latest Snips-AI NLU engine, with connection to an MQTT Broker." \
      org.label-schema.url="https://wuabit.com/" \
      org.label-schema.vcs-ref=$VCS_REF \
      org.label-schema.vcs-url="https://github.com/wuabit/snips-nlu-docker" \
      org.label-schema.vendor="Odianosen" \
      org.label-schema.version="1.0_${SNIPS_VERSION}" \
      org.label-schema.schema-version="1.0"

RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt

#RUN python -m snips_nlu download-language-entities en

ENTRYPOINT ["python3", "snips-nlu-app.py"]
CMD ["-c", "/config", "-d", "DEBUG"]
