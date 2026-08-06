"""
Configuration file for Hospital Management System
Stores database connection and Flask settings
"""

import os


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SESSION_PERMANENT = False
    SESSION_TYPE = "filesystem"


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

    # MySQL Database Configuration
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_USER = os.environ.get("DB_USER", "Twinkle")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "Twinkle@08")
    DB_NAME = os.environ.get("DB_NAME", "hospital_db")
    SESSION_TYPE = os.environ.get("SESSION_TYPE", "filesystem")


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "hospital_db")


# Configuration selector
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig
}
