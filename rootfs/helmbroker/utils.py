import os
import yaml
import json
import subprocess
import base64
import copy
import logging

from redis import client
from .config import REDIS_URL

logger = logging.getLogger(__name__)

REGISTRY_CONFIG_SUFFIX = '.config/helm/registry.json'
REPOSITORY_CACHE_SUFFIX = '.cache/helm/repository'
REPOSITORY_CONFIG_SUFFIX = '.config/helm/repository'


def command(cmd, *args, output_type="text"):
    status, output = subprocess.getstatusoutput("%s %s" % (cmd, " ".join(args)))
    if output_type == "yaml":
        return yaml.load(output, Loader=yaml.Loader)
    elif output_type == "json":
        return json.loads(output)
    return status, output


def helm(instance_id, *args, output_type="text"):
    from .database.query import get_instance_path
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
    return command("helm", *new_args, output_type=output_type)


def new_instance_lock(instance_id):
    redis = client.Redis.from_url(REDIS_URL)
    return redis.lock(instance_id)


def verify_parameters(allow_parameters, parameters):
    """verify parameters allowed or not"""
    def merge_parameters(parameters):
        raw_para_keys = []
        if "rawValues" in parameters:
            raw_values = yaml.safe_load(
                base64.b64decode(parameters["rawValues"]))
            raw_para_keys = _raw_values_format_keys(raw_values)
            parameters.pop("rawValues")
        return set(list(parameters.keys()) + raw_para_keys)

    if not parameters or not allow_parameters:
        return "", ""
    parameters = merge_parameters(copy.deepcopy(parameters))
    return (
        ",".join(_verify_allow_parameters(allow_parameters, parameters)),
        ",".join(_verify_required_parameters(allow_parameters, parameters)),
    )


def format_params_to_helm_args(instance_id, parameters, args):
    """format helm args"""
    from .database.savepoint import save_raw_values
    params = copy.deepcopy(parameters)
    if params and "rawValues" in params \
            and params.get("rawValues", ""):
        values = str(base64.b64decode(params["rawValues"]), "utf-8")
        raw_values_file = save_raw_values(instance_id, values)
        args.extend(["-f", raw_values_file])
        params.pop("rawValues")
    if params:
        for k, v in params.items():
            args.extend(["--set", f"{k}={v}"])
    return args


def _raw_values_format_keys(raw_values, prefix=''):
    """
    {'a': {'b': 1, 'c': {'d': 2, 'e': 3}}, 'f': 4}
    ->
    ['a.b', 'a.c.d', 'a.c.e', 'a.f']
    """
    keys = []
    for key, value in raw_values.items():
        new_prefix = prefix + '.' + key if prefix else key
        if isinstance(value, dict):
            keys.extend(_raw_values_format_keys(value, new_prefix))
        else:
            keys.append(new_prefix)
    return keys


def _verify_allow_parameters(allow_parameters, parameters):
    error_parameters = set()
    for parameter in parameters:
        error = True
        for allow_parameter in allow_parameters:
            if parameter.startswith("%s." % allow_parameter["name"]) \
                    or parameter == allow_parameter["name"]:
                error = False
                break
        if error:
            error_parameters.add(parameter)
    return error_parameters


def _verify_required_parameters(allow_parameters, parameters):
    error_parameters = set()
    for allow_parameter in allow_parameters:
        if allow_parameter.get("required", False):
            error = True
            for parameter in parameters:
                if parameter.startswith("%s." % allow_parameter["name"]) \
                        or parameter == allow_parameter["name"]:
                    error = False
                    break
            if error:
                error_parameters.add(allow_parameter["name"])
    return error_parameters
