import paho.mqtt.client as mqtt
import traceback
import argparse
import json
import sys
import os
import yaml
import time
import logging
import threading
import uuid
import io
import subprocess

from snips_nlu import SnipsNLUEngine
from snips_nlu.default_configs import CONFIG_EN
from snips_nlu.exceptions import NotTrained, DatasetFormatError

FORMAT = "%(asctime)s: %(levelname)s: %(message)s"
logging.basicConfig(format=FORMAT, level=logging.INFO, datefmt="%d-%b-%y %H:%M:%S")
logger = logging.getLogger("snips-nlu")
training = False

PARSE_REQUEST_TOPIC = "snips/nlu/request/parse"
PARSE_RESPONSE_TOPIC = "snips/nlu/response/parse"
TRAIN_REQUEST_TOPIC = "snips/nlu/request/train"
TRAIN_RESPONSE_TOPIC = "snips/nlu/response/train"
ENTITY_SET_REQUEST_TOPIC = "snips/nlu/set/request/entity"
ENTITY_SET_RESPONSE_TOPIC = "snips/nlu/set/response/entity"
INTENT_SET_REQUEST_TOPIC = "snips/nlu/set/request/intent"
INTENT_SET_RESPONSE_TOPIC = "snips/nlu/set/response/intent"
ENTITY_GET_REQUEST_TOPIC = "snips/nlu/get/request/entity"
ENTITY_GET_RESPONSE_TOPIC = "snips/nlu/get/response/entity"
INTENT_GET_REQUEST_TOPIC = "snips/nlu/get/request/intent"
INTENT_GET_RESPONSE_TOPIC = "snips/nlu/get/response/intent"
ENTITY_REMOVE_REQUEST_TOPIC = "snips/nlu/remove/request/entity"
ENTITY_REMOVE_RESPONSE_TOPIC = "snips/nlu/remove/response/entity"
INTENT_REMOVE_REQUEST_TOPIC = "snips/nlu/remove/request/intent"
INTENT_REMOVE_RESPONSE_TOPIC = "snips/nlu/remove/response/intent"
NLU_DATASET_FILE = "nlu_dataset.json"

# setup the snips engine
nlu_engine = SnipsNLUEngine(config=CONFIG_EN)
CONFIG = {}

def parseConfig(config_dir):
    """
    Parse and load the configuration file to get MQTT credentials
    """
    global CONFIG

    config_file = os.path.join(config_dir, "config.yaml")
    with open(config_file, "r") as stream:
        try:
            CONFIG = yaml.load(stream, Loader=yaml.SafeLoader)
            CONFIG["config_dir"] = config_dir
        except yaml.YAMLError as e:
            logger.warning(f"Unable to parse configuration file at {config_file}")
            logger.error(e)
            logger.debug(traceback.format_exc())
            sys.exit(1)

def on_connect(client, userdata, flags, rc):
    """
    The callback for when the client receives a CONNACK response from the MQTT server.
    """
    logger.info(f"Connected with result code {str(rc)}")

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    topics = [PARSE_REQUEST_TOPIC, TRAIN_REQUEST_TOPIC, ENTITY_SET_REQUEST_TOPIC,
            ENTITY_GET_REQUEST_TOPIC, INTENT_SET_REQUEST_TOPIC, INTENT_GET_REQUEST_TOPIC,
            ENTITY_REMOVE_REQUEST_TOPIC, INTENT_REMOVE_REQUEST_TOPIC]

    for topic in topics:
        (result, mid) = client.subscribe(topic)
        
        if result == 0:
            logger.info(f"Subscription to {topic} was Sucessful")
        else:    
            logger.warning(f"Subscription to {topic} was Unsucessful, with result {result}")
    
    client.publish("snips/nlu/started", json.dumps({"connected": True}), 0, retain=False)
    run_training(uuid.uuid4().hex)

def on_message(client, userdata, msg):
    """
    The callback for when a PUBLISH message is received from the MQTT server.
    """

    topic = str(msg.topic)
    message = msg.payload.decode().strip()

    logger.debug(f"Received command: {topic} {message}")
    payload = {}
    if message:
        try:
            payload = json.loads(message)
            if isinstance(payload, str):
                payload = {}
        except Exception as e:
            logger.error(e)
            logger.debug(traceback.format_exc())
            return

    qos = userdata.get("QOS", 0)

    command = topic.split("/")[-1]
    session_id = payload.get("session_id", uuid.uuid4().hex)
    
    if command == "train":
        run_training(session_id, qos)

    elif command == "parse":
        run_parsing(session_id, qos, payload)
    
    elif command in ("entity", "intent"):
        config_dir = userdata["config_dir"]
        run_process(command, topic.split("/")[2], config_dir, payload, qos)
        
def parse_text(session_id, qos, payload_data) -> None:
    """Parse the text sent"""
    
    global nlu_engine
    
    response = {"session_id": session_id, "status": "successful"}
    
    try:
        text = payload_data.get("text", "")
        intent_filter = payload_data.get("intent_filter")
        parsing = nlu_engine.parse(text, intents=intent_filter)
        response.update(parsing)
    except Exception as e:
        logger.error(e)
        logger.debug(traceback.format_exc())
        response.update({"status": "failed", "error": str(e)})
        
    res = json.dumps(response, indent=2)
    client.publish(PARSE_RESPONSE_TOPIC, res, qos, retain=False)

def get_all_yaml_files(dir):

    files = []

    for root, _, fs in os.walk(dir, topdown=False):
        for fl in fs:
            if fl.endswith(".yaml"):
                files.append(os.path.join(root, fl))
    
    return files

def process_files(task: str, target: str, name: str, folder: str) -> dict:
    """Used to get ot remove files"""

    response = {}

    if name == "all":
        files = get_all_yaml_files(folder)

    else:
        filename = f"{name}.yaml"
        files = [os.path.join(folder, filename)]

    logger.debug(f"Got {target} filenames as {files}")
    warnings = []
    data = []

    for file in files:
        if not os.path.isfile(file):
            logger.warning(f"Cannot {task} the file {file}, as it doesn't exist")
            warnings.append(f"{file} file doesn't exist")
            continue
        
        if task == "remove":
            os.remove(file)
        
        elif task == "get":
            with open(file, "r") as stream:
                data.append(yaml.load(stream, Loader=yaml.SafeLoader))

    if data != {}:
        response.update({target: data})

    if warnings != []:
        response.update({"warning": warnings})
        
    return response

def run_training(session_id, qos=0) -> None:
    """Used to run the training"""
    
    t = threading.Thread(target=train_nlu, args=(session_id, qos,), daemon=True)
    t.start()
    
def run_parsing(session_id, qos, payload_data) -> None:
    """Used to run the parsing of text"""
    
    t = threading.Thread(target=parse_text, args=(session_id, qos, payload_data,), daemon=True)
    t.start()
    
    
def run_process(command, task, config_dir, payload, qos) -> None:
    """Used to run the entity or intent processes"""
    
    args = (task, config_dir, payload, qos, )
    t = None
    
    if command == "entity":
        t = threading.Thread(target=process_entity, args=args, daemon=True)
    
    elif command == "intent":
        t = threading.Thread(target=process_intent, args=args, daemon=True)
    
    if t is not None:
        t.start()

def train_nlu(session_id, qos) -> None:
    global nlu_engine
    global training

    if training is True:
        logger.warning("Training already taking place, so will be ignoring command")
        return
    
    training = True
    
    logger.info("Training NLU")
    response = {"session_id": session_id, "status": "started"}
    started_response = {"session_id": session_id, "status": "started"}
    client.publish(TRAIN_RESPONSE_TOPIC, json.dumps(started_response), qos, retain=False)

    config_dir = CONFIG["config_dir"]
    dataset_file = os.path.join(config_dir, NLU_DATASET_FILE)
    training_folder = os.path.join(config_dir, "training")

    # first we get all files in the folder
    training_files = get_all_yaml_files(training_folder)        
    total_files = len(training_files)

    logger.info(f"Found a total of {total_files} files to train the NLU")

    if total_files == 0: # no wfiles found
        logger.warning("Could not find any files to train, exiting training")
        response.update({"status": "failed", "error": "No training files found to process"})
    
    else:
        all_training_files = " ".join(training_files)
        logger.debug(f"All Training Files {all_training_files}")
        
        cmd = f"snips-nlu generate-dataset en {all_training_files} > {dataset_file}"
        # now we need to use the cli to convert the ymal to json
        
        try:
            st = time.time()
            stdout = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE)
            completed = stdout.stdout.decode("utf-8").splitlines()
            tk1 = time.time() - st
            logger.info(f"Generated dataset sucessfully. Took {tk1}s with message {completed}")

            with io.open(dataset_file) as f:
                nlu_dataset = json.load(f)

            # train
            nlu_engine.fit(nlu_dataset)
            tk2 = time.time() - st
            response.update({"status": "success", "time_interval": tk2})
        
        except DatasetFormatError as d:
            logger.error(d)
            logger.debug(traceback.format_exc())
            response.update({"status": "failed", "error": str(d)})
            
        except NotTrained as n:
            logger.error(n)
            logger.debug(traceback.format_exc())
            response.update({"status": "failed", "error": str(n)})
        
        except KeyError as k:
            logger.error(k)
            logger.debug(traceback.format_exc())
            response.update({"status": "failed", "error": str(k)})
            
        except Exception as e:
            logger.error(e)
            logger.debug(traceback.format_exc())
            response.update({"status": "failed", "error": str(e)})               
    
    client.publish(TRAIN_RESPONSE_TOPIC, json.dumps(response), qos, retain=False)
    training = False

def process_entity(task: str, config_dir: str, data: dict, qos):
    """Process entity"""

    training_folder = os.path.join(config_dir, "training")
    entities_folder = os.path.join(training_folder, "entities")
    session_id = data.get("session_id", uuid.uuid4().hex)
    response = {"status": "successful", "session_id": session_id}
    response_topic = None
    entity_data = data.get("entity", {})

    if not isinstance(entity_data, dict):
        logger.warning("Entity Data must follow the right format {'entity': {}}. Cannot process request")
        return

    try:
        entity_name = entity_data.get("name")
        assert entity_data is not {}, ("Entity Data must be given, do ensure right format followed {'entity': {}}")
        assert entity_name is not None, ("Name of Entity must be given")
        
        response["name"] = entity_name

        if task == "set":
            entity_filename = f"{entity_name}.yaml"
            entity_file = os.path.join(entities_folder, entity_filename)
            logger.debug(f"Got entity filename as {entity_file} for set")

            response_topic = ENTITY_SET_RESPONSE_TOPIC

            with open(entity_file, "w") as stream:
                yaml.dump(entity_data, stream, Dumper=yaml.SafeDumper)

        elif task == "get":
            response_topic = ENTITY_GET_RESPONSE_TOPIC
            res = process_files(task, "entity", entity_name, entities_folder)
            response.update(res)
        
        elif task == "remove":
            response_topic = ENTITY_REMOVE_RESPONSE_TOPIC
            res = process_files(task, "entity", entity_name, entities_folder)
            response.update(res)

    except Exception as e:
        logger.error(e)
        logger.debug(traceback.format_exc())
        response.update({"status": "failed", "error": str(e)})

    if response_topic is not None:
        client.publish(response_topic, json.dumps(response), qos, retain=False)

def process_intent(task: str, config_dir: str, data: dict, qos):
    """Process intent"""
    training_folder = os.path.join(config_dir, "training")
    intents_folder = os.path.join(training_folder, "intents")
    session_id = data.get("session_id", uuid.uuid4().hex)
    response = {"status": "successful", "session_id": session_id}
    response_topic = None
    intent_data = data.get("intent", {})

    if not isinstance(intent_data, dict):
        logger.warning("Intent Data must follow the right format {'intent': {}}. Cannot process request")
        return

    try:
        intent_name = intent_data.get("name")
        assert intent_data is not {}, ("Intent Data must be given, do ensure right format followed {'intent': {}}")
        assert intent_name is not None, ("Name of Intent must be given")
        
        response["name"] = intent_name

        if task == "set":
            # expecting a json data to be turned into yaml
            response_topic = INTENT_SET_RESPONSE_TOPIC
            intent_filename = f"{intent_name}.yaml"
            intent_file = os.path.join(intents_folder, intent_filename)
            logger.debug(f"Got intent filename as {intent_file} for set")

            with open(intent_file, "w") as stream:
                yaml.dump(intent_data, stream, Dumper=yaml.SafeDumper)

        elif task == "get":
            # expecting a json data to be turned into yaml
            response_topic = INTENT_GET_RESPONSE_TOPIC
            res = process_files(task, "intent", intent_name, intents_folder)
            response.update(res)
        
        elif task == "remove":
            response_topic = ENTITY_REMOVE_RESPONSE_TOPIC
            res = process_files(task, "intent", intent_name, intents_folder)
            response.update(res)

    except Exception as e:
        logger.error(e)
        logger.debug(traceback.format_exc())
        response.update({"status": "failed", "error": str(e)})

    if response_topic is not None:
        client.publish(response_topic, json.dumps(response), qos, retain=False)

"""
Initialize the MQTT object and connect to the server, looping forever waiting for messages
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config_file", help="The configuration file to use", type=str, default=None, required=True)
    parser.add_argument("-d", "--debug", help="The Log level to make use of", type=str, default="INFO", choices=["DEBUG", "ERROR", "WARNING", "CRITICAL"])

    args = parser.parse_args()
    config_dir = args.config_file
    log_level = args.debug
    
    logger.setLevel(log_level)
    parseConfig(config_dir)

    BROKER = CONFIG.get("MQTT_BROKER")
    PORT = CONFIG.get("MQTT_PORT", 1883)
    USERNAME = CONFIG.get("MQTT_USERNAME")
    PASSWORD = CONFIG.get("MQTT_PASSWORD")
    CLIENTNAME = CONFIG.get("MQTT_CLIENTNAME", "snips-nlu")
    CA_CERT = CONFIG.get("MQTT_CA_CERT")
    TLS_CERTFILE = CONFIG.get("TLS_CERTFILE")
    TLS_KEYFILE = CONFIG.get("TLS_KEYFILE")
    VERIFY_CERT = CONFIG.get("VERIFY_CERT", True)

    client = mqtt.Client(client_id=CLIENTNAME)
    client.on_connect = on_connect
    client.on_message = on_message

    set_tls = False
    auth = {}
    if CA_CERT is not None:
        auth.update({"ca_certs": CA_CERT})
        set_tls = True

    if TLS_CERTFILE is not None:
        auth.update({"certfile": TLS_CERTFILE})
        set_tls = True

    if TLS_KEYFILE is not None:
        auth.update({"keyfile": TLS_KEYFILE})
        set_tls = True

    if set_tls is True:
        client.tls_set(**auth)

        if not VERIFY_CERT:
            client.tls_insecure_set(not VERIFY_CERT)

    if USERNAME and PASSWORD:
        client.username_pw_set(username=USERNAME, password=PASSWORD)
    
    logger.info("Starting SNIPS-NLU")
    client.user_data_set(CONFIG)

    while True:
        try:
            client.connect(BROKER, PORT, 60)
            client.loop_forever()
            break
        except Exception:
            logger.error("There was an error while attempting to connect to broker")
            logger.debug(traceback.format_exc())
            sys.exit()