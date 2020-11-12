# Copyright 2020-     Robot Framework Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import os
import sys
import time
from pathlib import Path
from subprocess import STDOUT, Popen
from typing import TYPE_CHECKING

import grpc  # type: ignore
from backports.cached_property import cached_property

import Browser.generated.playwright_pb2_grpc as playwright_pb2_grpc
from Browser.generated.playwright_pb2 import Request

from .base import LibraryComponent

if TYPE_CHECKING:
    from .browser import Browser

from .utils import find_free_port, logger


class Playwright(LibraryComponent):
    """A wrapper for communicating with nodejs Playwirght process."""

    def __init__(self, library: "Browser", enable_playwright_debug: bool):
        LibraryComponent.__init__(self, library)
        self.enable_playwright_debug = enable_playwright_debug
        self.ensure_node_dependencies()
        self.port = None

    @cached_property
    def _playwright_process(self) -> Popen:
        process = self.start_playwright()
        self.wait_until_server_up()
        return process

    def ensure_node_dependencies(self):
        """
        rfbrowser_dir = Path(__file__).parent
        installation_dir = rfbrowser_dir / "wrapper"
        # This second application of .parent is necessary to find out that a developer setup has node_modules correctly
        project_folder = rfbrowser_dir.parent
        subfolders = os.listdir(project_folder) + os.listdir(installation_dir)

        if "node_modules" in subfolders:
            return
        raise RuntimeError(
            f"Could not find node dependencies in installation directory `{installation_dir}.` "
            "Run `rfbrowser init` to install the dependencies."
        )"""

    def start_playwright(self):
        current_dir = Path(__file__).parent
        workdir = current_dir / "wrapper"

        operating_system = sys.platform
        if operating_system == "windows":
            playwright_script = workdir / "robotframework-playwright-win.exe"
        elif operating_system == "darwin":
            playwright_script = workdir / "robotframework-playwright-macos"
        elif operating_system == "linux":
            playwright_script = workdir / "robotframework-playwright-linux"
        else:
            raise NotImplementedError("Operating system not supported")

        logfile = open(Path(self.outputdir, "playwright-log.txt"), "w")
        port = str(find_free_port())
        if self.enable_playwright_debug:
            os.environ["DEBUG"] = "pw:api"

        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(workdir / "browser_binaries")
        logger.info(f"Starting Browser process {playwright_script} using port {port}")
        self.port = port
        return Popen(
            [str(playwright_script), port],
            shell=False,
            cwd=workdir,
            env=os.environ,
            stdout=logfile,
            stderr=STDOUT,
        )

    def wait_until_server_up(self):
        for i in range(50):
            with grpc.insecure_channel(f"localhost:{self.port}") as channel:
                try:
                    stub = playwright_pb2_grpc.PlaywrightStub(channel)
                    response = stub.Health(Request().Empty())
                    logger.debug(
                        f"Connected to the playwright process at port {self.port}: {response}"
                    )
                    return
                except grpc.RpcError as err:
                    logger.debug(err)
                    time.sleep(0.1)
        raise RuntimeError(
            f"Could not connect to the playwright process at port {self.port}."
        )

    @contextlib.contextmanager
    def grpc_channel(self):
        """Yields a PlayWrightstub on a newly initialized channel

        Acts as a context manager, so channel is closed automatically when control returns.
        """
        returncode = self._playwright_process.poll()
        if returncode is not None:
            raise ConnectionError(
                "Playwright process has been terminated with code {}".format(returncode)
            )
        channel = grpc.insecure_channel(f"localhost:{self.port}")
        try:
            yield playwright_pb2_grpc.PlaywrightStub(channel)
        except Exception as e:
            raise AssertionError(self.get_reason(e))
        finally:
            channel.close()

    def get_reason(self, err):
        try:
            metadata = err.trailing_metadata()
            for element in metadata:
                if element.key == "reason":
                    return element.value
        except AttributeError:
            pass
        try:
            return err.details()
        except TypeError:
            return err.details
        except AttributeError:
            pass
        return str(err)

    def close(self):
        logger.debug("Closing all open browsers, contexts and pages in Playwright")
        with self.grpc_channel() as stub:
            response = stub.CloseAllBrowsers(Request().Empty())
            logger.info(response.log)

        logger.debug("Closing Playwright process")
        self._playwright_process.kill()
        logger.debug("Playwright process killed")
