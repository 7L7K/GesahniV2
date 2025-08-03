# GesahniV2 application package
# app/__init__.py
import importlib, sys
sys.modules[__name__ + ".skills"] = importlib.import_module(".skills", __name__)
