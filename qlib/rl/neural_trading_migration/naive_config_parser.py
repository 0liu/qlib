# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
import platform
import shutil
import sys
import tempfile
from importlib import import_module

import yaml


def merge_a_into_b(a: dict, b: dict) -> dict:
    b = b.copy()
    for k, v in a.items():
        if isinstance(v, dict) and k in b:
            v.pop("_delete_", False)  # TODO: make this more elegant
            b[k] = merge_a_into_b(v, b[k])
        else:
            b[k] = v
    return b


def check_file_exist(filename: str, msg_tmpl: str = 'file "{}" does not exist') -> None:
    if not os.path.isfile(filename):
        raise FileNotFoundError(msg_tmpl.format(filename))


def parse_backtest_config(path: str) -> dict:
    abs_path = os.path.abspath(path)
    check_file_exist(abs_path)

    file_ext_name = os.path.splitext(abs_path)[1]
    if file_ext_name not in (".py", ".json", ".yaml", ".yml"):
        raise IOError("Only py/yml/yaml/json type are supported now!")

    with tempfile.TemporaryDirectory() as tmp_config_dir:
        tmp_config_file = tempfile.NamedTemporaryFile(dir=tmp_config_dir, suffix=file_ext_name)
        if platform.system() == "Windows":
            tmp_config_file.close()

        tmp_config_name = os.path.basename(tmp_config_file.name)
        shutil.copyfile(abs_path, tmp_config_file.name)

        if abs_path.endswith(".py"):
            tmp_module_name = os.path.splitext(tmp_config_name)[0]
            sys.path.insert(0, tmp_config_dir)
            module = import_module(tmp_module_name)
            sys.path.pop(0)

            config = {k: v for k, v in module.__dict__.items() if not k.startswith("__")}

            del sys.modules[tmp_module_name]
        else:
            config = yaml.safe_load(open(os.path.join(tmp_config_dir, tmp_config_file.name)))

    if "_base_" in config:
        base_file_name = config.pop("_base_")
        if not isinstance(base_file_name, list):
            base_file_name = [base_file_name]

        for f in base_file_name:
            base_config = parse_backtest_config(os.path.join(os.path.dirname(abs_path), f))
            config = merge_a_into_b(a=config, b=base_config)

    return config


def _convert_all_list_to_tuple(config: dict) -> dict:
    for k, v in config.items():
        if isinstance(v, list):
            config[k] = tuple(v)
        elif isinstance(v, dict):
            config[k] = _convert_all_list_to_tuple(v)
    return config


def get_backtest_config_fromfile(path: str) -> dict:
    backtest_config = parse_backtest_config(path)

    exchange_config_default = {
        "open_cost": 0.0005,
        "close_cost": 0.0015,
        "min_cost": 5.0,
        "trade_unit": 100.0,
        "cash_limit": None,
        "generate_report": False,
    }
    backtest_config["exchange"] = merge_a_into_b(a=backtest_config["exchange"], b=exchange_config_default)
    backtest_config["exchange"] = _convert_all_list_to_tuple(backtest_config["exchange"])

    backtest_config_default = {
        "debug_single_stock": None,
        "debug_single_day": None,
        "concurrency": -1,
        "multiplier": 1.0,
        "output_dir": "outputs/",
        # "runtime": {},
    }
    backtest_config = merge_a_into_b(a=backtest_config, b=backtest_config_default)

    return backtest_config


def convert_instance_config(config: object) -> object:
    if isinstance(config, dict):
        if "type" in config:
            type_name = config["type"]
            if "." in type_name:
                idx = type_name.rindex(".")
                module_path, class_name = type_name[:idx], type_name[idx + 1 :]
            else:
                module_path, class_name = "", type_name

            kwargs = {}
            for k, v in config.items():
                if k == "type":
                    continue
                kwargs[k] = convert_instance_config(v)
            return {
                "class": class_name,
                "module_path": module_path,
                "kwargs": kwargs,
            }
        else:
            return {k: convert_instance_config(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [convert_instance_config(item) for item in config]
    elif isinstance(config, tuple):
        return tuple([convert_instance_config(item) for item in config])
    else:
        return config