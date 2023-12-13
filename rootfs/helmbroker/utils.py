import os
import fcntl
import yaml
import json
import subprocess
import time
import base64
import copy

from jsonschema import validate
from .config import INSTANCES_PATH, ADDONS_PATH


REGISTRY_CONFIG_SUFFIX = '.config/helm/registry.json'
REPOSITORY_CACHE_SUFFIX = '.cache/helm/repository'
REPOSITORY_CONFIG_SUFFIX = '.config/helm/repository'


def command(cmd, *args, output_type="text"):
    status, output = subprocess.getstatusoutput("%s %s" % (cmd, " ".join(args))) # noqa
    if output_type == "yaml":
        return yaml.load(output, Loader=yaml.Loader)
    elif output_type == "json":
        return json.loads(output)
    return status, output


get_instance_path = lambda instance_id: os.path.join(INSTANCES_PATH, instance_id) # noqa
get_instance_file = lambda instance_id: os.path.join(get_instance_path(instance_id), "instance.json") # noqa
get_chart_path = lambda instance_id: os.path.join(get_instance_path(instance_id), "chart") # noqa
get_plan_path = lambda instance_id: os.path.join(get_instance_path(instance_id), "plan") # noqa


def helm(instance_id, *args, output_type="text"):
    instance_path = get_instance_path(instance_id)
    new_args = []
    new_args.extend(args)
    new_args.extend([
        "--registry-config",
        os.path.join(instance_path, REGISTRY_CONFIG_SUFFIX),
        "--repository-cache",
        os.path.join(instance_path, REPOSITORY_CACHE_SUFFIX),
        "--repository-config",
        os.path.join(instance_path, REPOSITORY_CONFIG_SUFFIX),
    ])
    return command("helm", *args, output_type=output_type)


INSTANCE_META_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "details": {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "context": {"type": "object"},
                "parameters": {
                    'oneOf': [{'type': 'object'}, {'type': 'null'}]
                },
            },
            "required": [
                "service_id", "plan_id", "context"
            ]
        },
        "last_operation": {
            "type": "object",
            "properties": {
                "state": {"type": "string"},
                "operation": {"type": "string"},
                "description": {"type": "string"}
            }
        },
        "last_modified_time": {"type": "number"}
    },
}


def load_instance_meta(instance_id):
    file = get_instance_file(instance_id)
    with open(file) as f:
        data = json.loads(f.read())
        validate(instance=data, schema=INSTANCE_META_SCHEMA)
        return data


def dump_instance_meta(instance_id, data):
    data["last_modified_time"] = time.time()
    file = get_instance_file(instance_id)
    validate(instance=data, schema=INSTANCE_META_SCHEMA)
    with open(file, "w") as f:
        f.write(json.dumps(data, sort_keys=True, indent=2))


def dump_raw_values(instance_id, data):
    timestamp = time.time()
    instance_path = get_instance_path(instance_id)
    file = f"{instance_path}/raw-values-{timestamp}.yaml"
    with open(file, "w") as f:
        f.write(data)
    return file


BINDING_META_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "credentials": {
            "type": "object",
        },
        "last_operation": {
            "type": "object",
            "properties": {
                "state": {"type": "string"},
                "description": {"type": "string"}
            }
        },
        "last_modified_time": {"type": "number"}
    }
}


def load_binding_meta(instance_id):
    file = os.path.join(get_instance_path(instance_id), "binding.json")
    with open(file, 'r') as f:
        data = json.loads(f.read())
        validate(instance=data, schema=INSTANCE_META_SCHEMA)
        return data


def dump_binding_meta(instance_id, data):
    data["last_modified_time"] = time.time()
    file = os.path.join(get_instance_path(instance_id), "binding.json")
    validate(instance=data, schema=INSTANCE_META_SCHEMA)
    with open(file, "w") as f:
        f.write(json.dumps(data, sort_keys=True, indent=2))


ADDONS_META_SCHEMA = {
    "type": "object",
    "patternProperties": {
        ".*": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "version": {"type": "string"},
            "bindable": {"type": "boolean"},
            "instances_retrievable": {"type": "boolean"},
            "bindings_retrievable": {"type": "boolean"},
            "allow_context_updates": {"type": "boolean"},
            "description": {"type": "string"},
            "tags": {"type": "string"},
            "requires": {"type": "array"},
            "metadata": {"type": "object"},
            "plan_updateable": {"type": "boolean"},
            "dashboard_client": {"type": "object"},
            "plans": {
                "type": "object",
                "id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "metadata": {"type": "object"},
                "free": {"type": "boolean"},
                "bindable": {"type": "boolean"},
                "binding_rotatable": {"type": "boolean"},
                "plan_updateable": {"type": "boolean"},
                "schemas": {"type": "object"},
                "maximum_polling_duration": {"type": "integer"},
                "maintenance_info": {"type": "object"},
                "required": [
                    "id", "name", "description"
                ]
            },
            "required": [
                "id", "name", "description", "bindable", "version", "plans"
            ]
        }
    }
}


def load_addons_meta():
    file = os.path.join(ADDONS_PATH, "addons.json")
    with open(file, 'r') as f:
        data = json.loads(f.read())
        if not data:
            return {}
        validate(instance=data, schema=INSTANCE_META_SCHEMA)
        return data


def dump_addons_meta(data):
    file = os.path.join(ADDONS_PATH, "addons.json")
    validate(instance=data, schema=INSTANCE_META_SCHEMA)
    with open(file, "w") as f:
        f.write(json.dumps(data, sort_keys=True, indent=2))


def get_addon_meta(service_id):
    services = load_addons_meta()
    service = [addon for addon in [addons for _, addons in services.items()]
               if addon['id'] == service_id][0]
    return service


def get_addon_path(service_id, plan_id):
    service = get_addon_meta(service_id)
    plan = [plan for plan in service['plans'] if plan['id'] == plan_id][0]
    service_name = f'{service["name"]}-{service["version"]}'
    plan_name = plan['name']
    service_path = f'{ADDONS_PATH}/{service_name}/chart/{service["name"]}'
    plan_path = f'{ADDONS_PATH}/{service_name}/plans/{plan_name}'
    return service_path, plan_path


def get_addon_name(service_id):
    service = get_addon_meta(service_id)
    return service['name']


def get_addon_updateable(service_id):
    service = get_addon_meta(service_id)
    return service.get('plan_updateable', False)


def get_addon_bindable(service_id):
    service = get_addon_meta(service_id)
    return service.get('bindable', False)


def get_addon_allow_paras(service_id):
    service = get_addon_meta(service_id)
    return service.get('allow_parameters', [])


def get_addon_archive(service_id):
    service = get_addon_meta(service_id)
    return service.get('archive', False)


def get_cred_value(ns, source):
    if source.get('serviceRef'):
        return get_service_key_value(ns, source['serviceRef'])
    if source.get('configMapRef'):
        return get_config_map_key_value(ns, source['configMapRef'])
    if source.get('secretKeyRef'):
        return get_secret_key_value(ns, source['secretKeyRef'])
    return -1, 'invalid valueFrom'


def get_service_key_value(ns, service_ref):
    args = [
        "get", "svc", service_ref['name'], "-n", ns, '-o', f"jsonpath=\'{service_ref['jsonpath']}\'", # noqa
    ]
    return command("kubectl", *args)


def get_config_map_key_value(ns, config_map_ref):
    args = [
        "get", "cm", config_map_ref['name'], "-n", ns, '-o', f"jsonpath=\'{config_map_ref['jsonpath']}\'", # noqa
    ]
    return command("kubectl", *args)


def get_secret_key_value(ns, secret_ref):
    args = [
        "get", "secret", secret_ref['name'], "-n", ns, '-o', f"jsonpath=\'{secret_ref['jsonpath']}\'", # noqa
    ]
    status, output = command("kubectl", *args)
    if status == 0:
        output = base64.b64decode(output).decode()
    return status, output


class InstanceLock(object):

    def __init__(self, instance_id):
        self.instance_id = instance_id

    def __enter__(self):
        self.fileno = open(
            os.path.join(INSTANCES_PATH, self.instance_id, "instance.lock"),
            "w"
        )
        fcntl.flock(self.fileno, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        fcntl.flock(self.fileno, fcntl.LOCK_UN)

    def __del__(self):
        if hasattr(self, "fileno"):
            fcntl.flock(self.fileno, fcntl.LOCK_UN)


def verify_parameters(allow_paras, paras):
    """verify parameters allowed or not"""
    if not paras or not allow_paras:
        return ""
    tmp_paras = copy.deepcopy(paras)
    # raw_values
    raw_para_keys = []
    if "rawValues" in tmp_paras:
        raw_values = yaml.safe_load(base64.b64decode(tmp_paras["rawValues"]))
        raw_para_keys = raw_values_format_keys(raw_values)
        tmp_paras.pop("rawValues")

    para_keys = set(list(tmp_paras.keys()) + raw_para_keys)
    para_keys = [k + "." for k in para_keys]
    allow_para_keys = [allow_para["name"] + "." for allow_para in allow_paras]  # noqa

    not_allow_paras = []
    for para_key in para_keys:
        for allow_para_key in allow_para_keys:
            # sub string, inclusion relationship
            if not para_key.startswith(allow_para_key):
                not_allow_paras.append(para_key)
        not_allow_paras = list(set(not_allow_paras))
        for allow_para_key in allow_para_keys:
            # sub string, inclusion relationship
            if para_key.startswith(allow_para_key) and para_key in not_allow_paras: # noqa
                not_allow_paras.remove(para_key)
    not_allow_keys = ",".join(not_allow_paras)
    return not_allow_keys


def raw_values_format_keys(raw_values, prefix=''):
    """
    {'a': {'b': 1, 'c': {'d': 2, 'e': 3}}, 'f': 4}
    ->
    ['a.b', 'a.c.d', 'a.c.e', 'a.f']
    """
    keys = []
    for key, value in raw_values.items():
        new_prefix = prefix + '.' + key if prefix else key
        if isinstance(value, dict):
            keys.extend(raw_values_format_keys(value, new_prefix))
        else:
            keys.append(new_prefix)
    return keys


def format_paras_to_helm_args(instance_id, parameters, args):
    """

    """
    params = copy.deepcopy(parameters)
    if params and "rawValues" in params \
            and params.get("rawValues", ""):
        values = str(base64.b64decode(params["rawValues"]), "utf-8")  # noqa
        raw_values_file = dump_raw_values(instance_id, values)
        args.extend(["-f", raw_values_file])
        params.pop("rawValues")
    if params:
        for k, v in params.items():
            args.extend(["--set", f"{k}={v}"])
    return args
