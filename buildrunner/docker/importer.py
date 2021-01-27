"""
Copyright (C) 2020 Adobe
"""

import yaml

import docker

from buildrunner.docker import new_client
from buildrunner.errors import BuildRunnerProcessingError
from buildrunner.utils import is_dict


class DockerImporter:
    """
    An object that orchestrates importing a Docker image from
    a tar file.
    """

    def __init__(
            self,
            src,
            dockerd_url=None,
            timeout=None,
    ):
        self.src = src
        self.docker_client = new_client(
            dockerd_url=dockerd_url,
            timeout=timeout,
        )
        self.image = None

    def import_image(self):
        """
        Run a docker import using the configured src archive.
        """

        try:
            import_return = self.docker_client.import_image(self.src)
        except docker.errors.APIError as apie:
            raise BuildRunnerProcessingError(
                f'Error importing image from archive file {self.src}: {apie}'
            ) from apie
        if not is_dict(import_return):
            import_return = yaml.load(import_return)
        if 'status' not in import_return:
            raise BuildRunnerProcessingError(
                f'Error importing image from archive file {self.src}'
            )
        return import_return['status']
