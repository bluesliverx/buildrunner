"""
Copyright (C) 2015 Adobe
"""
from __future__ import absolute_import
import json
import os

import buildrunner.docker
from buildrunner.errors import (
    BuildRunnerConfigurationError,
    BuildRunnerProcessingError,
)
from buildrunner.steprunner.tasks import BuildStepRunnerTask
from buildrunner.utils import is_dict


class PushBuildStepRunnerTask(BuildStepRunnerTask):
    """
    Class used to push the resulting image (either from the build task, or if
    there is a run task, the snapshot of the resulting run container) to the
    given registry/repository.
    """


    def __init__(self, step_runner, config):
        super(PushBuildStepRunnerTask, self).__init__(step_runner, config)
        self._docker_client = buildrunner.docker.new_client()
        self._repository = None
        self._insecure_registry = None
        self._tags = []
        if is_dict(config):
            if 'repository' not in config:
                raise BuildRunnerConfigurationError(
                    'Docker push configuration must at least specify a '
                    '"repository" attribute'
                )
            self._repository = config['repository']

            if 'tags' in config:
                self._tags = config['tags']

            if 'insecure_registry' in config:
                self._insecure_registry = config['insecure_registry'] is True
        else:
            self._repository = config


    def run(self, context):
        self.step_runner.log.write(
            'Pushing resulting image to "%s".\n' % self._repository
        )

        # first see if a run task produced an image (via a post-build config)
        if 'run-image' in context:
            image_to_use = context.get('run-image')
        # next see if there was a run task, committing the end state of the
        # container as the image to use
        elif 'run_runner' in context:
            image_to_use = context['run_runner'].commit(self.step_runner.log)
        # finally see if we have an image from a build task
        else:
            image_to_use = context.get('image', None)

        # validate we have an image
        if not image_to_use:
            raise BuildRunnerProcessingError(
                'Cannot find an image to tag/push from a previous task'
            )
        self.step_runner.log.write(
            'Using image %s for tagging\n' % (
                image_to_use,
            )
        )

        # determine internal tag based on source control information and build
        # number
        self._tags.append(self.step_runner.build_runner.build_id)

        # tag the image
        for _tag in self._tags:
            self.step_runner.log.write(
                'Tagging image "%s" with repository:tag "%s:%s"\n' % (
                    image_to_use,
                    self._repository,
                    _tag,
                )
            )
            self._docker_client.tag(
                image_to_use,
                self._repository,
                tag=_tag,
                force=True,
            )

        # see if we should push the image to a remote repository
        if self.step_runner.build_runner.push:
            # push the image
            stream = self._docker_client.push(
                self._repository,
                stream=True,
                insecure_registry=self._insecure_registry,
            )
            previous_status = None
            for msg_str in stream:
                for msg in msg_str.split("\n"):
                    if msg:
                        msg = json.loads(msg)
                        if 'status' in msg:
                            if msg['status'] == previous_status:
                                continue
                            self.step_runner.log.write(msg['status'] + '\n')
                            previous_status = msg['status']
                        elif 'errorDetail' in msg:
                            error_detail = "Error pushing image: %s\n" % (
                                msg['errorDetail']
                            )
                            self.step_runner.log.write("\n" + error_detail)
                            self.step_runner.log.write((
                                "This could be because you are not authenticated "
                                "with the given Docker registry (try 'docker login "
                                "<registry>')\n\n"
                            ))
                            raise BuildRunnerProcessingError(error_detail)
                        else:
                            self.step_runner.log.write(str(msg) + '\n')

            # cleanup the image and tag
            self._docker_client.remove_image(
                image_to_use,
                noprune=True,
                force=True,
            )
        else:
            self.step_runner.log.write(
                'push not requested--not cleaning up image locally\n'
            )

        # add image as artifact
        self.step_runner.build_runner.add_artifact(
            os.path.join(self.step_runner.name, image_to_use),
            {
                'type': 'docker-image',
                'docker:image': image_to_use,
                'docker:repository': self._repository,
                'docker:tags': self._tags,
            },
        )
