#########
# Copyright (c) 2017 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

from os.path import join

from .. import (
    SERVICE_USER,
    SERVICE_GROUP,
    HOME_DIR_KEY,
    VENV
)

from ..service_names import STAGE, MANAGER, RESTSERVICE

from ...config import config
from ...logger import get_logger
from ...constants import BASE_LOG_DIR, BASE_RESOURCES_PATH, CLOUDIFY_GROUP

from ...utils import sudoers
from ...utils import common, files
from ...utils.systemd import systemd
from ...utils.network import wait_for_port
from ...utils.users import (delete_service_user,
                            delete_group)
from ...utils.logrotate import set_logrotate, remove_logrotate

logger = get_logger(STAGE)

STAGE_USER = '{0}_user'.format(STAGE)
STAGE_GROUP = '{0}_group'.format(STAGE)

HOME_DIR = join('/opt', 'cloudify-{0}'.format(STAGE))
LOG_DIR = join(BASE_LOG_DIR, STAGE)
RESOURCES_DIR = join(HOME_DIR, 'resources')
STAGE_RESOURCES = join(BASE_RESOURCES_PATH, STAGE)

NODE_EXECUTABLE_PATH = '/usr/bin/node'


def _create_paths():
    common.mkdir(HOME_DIR)
    common.mkdir(RESOURCES_DIR)


def _set_community_mode():
    premium_edition = config[MANAGER]['premium_edition']
    community_mode = '' if premium_edition else '-mode community'

    # This is used in the stage systemd service file
    config[STAGE]['community_mode'] = community_mode


def _install():
    _create_paths()


def _deploy_script(script_name, description):
    sudoers.deploy_sudo_command_script(
        script_name,
        description,
        component=STAGE,
        allow_as=STAGE_USER
    )
    common.chmod('a+rx', join(STAGE_RESOURCES, script_name))
    common.sudo(['usermod', '-aG', CLOUDIFY_GROUP, STAGE_USER])


def _deploy_scripts():
    config[STAGE][HOME_DIR_KEY] = HOME_DIR
    _deploy_script(
        'restore-snapshot.py',
        'Restore stage directories from a snapshot path'
    )
    _deploy_script(
        'make-auth-token.py',
        'Update auth token for stage user'
    )


def _allow_snapshot_restore_to_restore_token(rest_service_python):
    sudoers.allow_user_to_sudo_command(
        rest_service_python,
        'Snapshot update auth token for stage user',
        allow_as=STAGE_USER
    )


def _create_auth_token(rest_service_python):
    common.run([
        'sudo', '-u', STAGE_USER, rest_service_python,
        join(STAGE_RESOURCES, 'make-auth-token.py')
    ])


def _run_db_migrate():
    backend_dir = join(HOME_DIR, 'backend')
    common.run(
        'cd {0}; /usr/bin/npm run db-migrate'.format(backend_dir),
        shell=True
    )


def _start_and_validate_stage():
    _set_community_mode()
    # Used in the service template
    config[STAGE][SERVICE_USER] = STAGE_USER
    config[STAGE][SERVICE_GROUP] = STAGE_GROUP
    systemd.configure(STAGE)

    logger.info('Starting Stage service...')
    systemd.restart(STAGE)
    wait_for_port(8088)


def _configure():
    files.copy_notice(STAGE)
    set_logrotate(STAGE)
    _deploy_scripts()
    rest_service_python = join(config[RESTSERVICE][VENV], 'bin', 'python')
    _allow_snapshot_restore_to_restore_token(rest_service_python)
    _create_auth_token(rest_service_python)
    _run_db_migrate()
    _start_and_validate_stage()


def install():
    logger.notice('Installing Stage...')
    _install()
    _configure()
    logger.notice('Stage successfully installed')


def configure():
    logger.notice('Configuring Stage...')
    _configure()
    logger.notice('Stage successfully configured')


def remove():
    logger.notice('Removing Stage...')
    files.remove_notice(STAGE)
    remove_logrotate(STAGE)
    systemd.remove(STAGE)
    delete_service_user(STAGE_USER)
    delete_group(STAGE_GROUP)
    files.remove_files([HOME_DIR, LOG_DIR, NODE_EXECUTABLE_PATH])
    logger.notice('Stage successfully removed')
