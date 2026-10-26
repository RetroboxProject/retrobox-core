from __future__ import annotations

from typing import ClassVar

class BaseRetroboxException(Exception):
    EXIT_CODE: ClassVar = 1

    @property
    def exit_code(self) -> int:
        return self.EXIT_CODE

class RetroboxException(BaseRetroboxException):
    @property
    def exit_code(self) -> int:
        if self.args and isinstance(self.args[0], str):
            return 250

        return self.EXIT_CODE

class UnexpectedEmulatorExit(BaseRetroboxException):
    EXIT_CODE = 200

class BadCommandLineArguments(BaseRetroboxException):
    EXIT_CODE = 201

class InvalidConfiguration(BaseRetroboxException):
    EXIT_CODE = 202

class UnknownEmulator(BaseRetroboxException):
    EXIT_CODE = 203

class MissingEmulator(BaseRetroboxException):
    EXIT_CODE = 204

class MissingCore(BaseRetroboxException):
    EXIT_CODE = 205
