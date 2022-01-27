## Snips NLU docker Python App

This docker container, runs a python application that contains the latest Snips NLU and allows to interact with it over MQTT

Setup
-----

To setup, simply create a yaml file `config.yaml` and enter in your MQTT broker details following the examples below

```yaml
MQTT_BROKER: xxx.xxx.xxx.xxx
MQTT_PORT: 1883
MQTT_USERNAME: username
MQTT_PASSWORD: password
MQTT_CLIENTNAME: snips-nlu
```

A volume config should be passed on to the docker container, within which the config and training files will reside
The create two folders
- `training/entities`: This is where the entities will reside
- `training/intents`: This is where the intents will reside

Then using the training MQTT topic, instruct it to train.

The application accepts each intent and entity as a separate file in their respective directives. 
Documentation on writing entities and intents can be found on Snips documentation [here](https://snips-nlu.readthedocs.io/en/latest/)

MQTT Topics
-----------

Outlined below are the topics used and their use cases

| Topic                    | Use                               | Payload Type | Example                                                             |
|--------------------------|-----------------------------------|--------------|---------------------------------------------------------------------|
| snips/nlu/request/parse  | Used to send data to app to parse | dict         | {"text": "turn on my light", "session_id": 1234}                    |
| snips/nlu/response/parse | Response from parsing the text    | dict         | {"status": "success", "intent": "turnOnLights", "intent_slots": {}} |
| snips/nlu/request/train  | Used to instruct Snips to train   | str          | {"session_id": 1234}                                                |
| snips/nlu/response/train | Response from snips training      | dict         | {"session_id": 1234, "status": "success"}                           |



Build
------------

```bash
$ docker build -t odianosen/snips-nlu-app .
```

## License

View [license information](https://github.com/snipsco/snips-nlu#licence) for the software contained in this image.

