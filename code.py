"""Podhawk allows you to keep image and container up-to-date."""
from json import loads
from subprocess import PIPE, STDOUT, check_output, run
from sys import exit
from typing import List


def remove_old_container(old_ctn_id):
    """Remove old container."""
    print(f'Removing old container {old_ctn_id}')
    remove = run(['podman', 'rm', old_ctn_id],
                 capture_output=True).stdout.decode('utf-8')
    print(f'Removing … {remove}')


def post_healthcheck(old_ctn_id, new_ctn_id, status):
    """After healthcheck, take the right decision."""
    if 'NA' in status:
        print('No healthcheck defined in this image… '
              'We continue at your own risk')
        remove_old_container(old_ctn_id)
    elif 'true' in status:
        print('Healthcheck success')
        remove_old_container(old_ctn_id)
    else:
        print(f'Healthcheck failed, restarting old container {old_ctn_id}')
        print('New container forced to stop and not removed '
              'to permit you to analyze logs')
        run(['podman', 'stop', new_ctn_id])
        start_old = run(['podman', 'start', old_ctn_id],
                        capture_output=True).stdout.decode('utf-8')
        print(f'Starting … {start_old}')


def health_check(container_id):
    """Analyze healthcheck status and return value needed by post_healthcheck.

    Args:
        container_id (str): new container id

    Returns:
        A string that permit to know in which situation we are
    """
    status: str = 'false'
    for i in range(3):
        output = run(['podman', 'healthcheck', 'run', container_id],
                     stdout=PIPE, stderr=STDOUT).stdout.decode('utf-8')
        print(f'({container_id}) healthcheck {i}/3: {output}')
        if 'has no defined healthcheck' in output:
            return 'NA'
        elif 'unhealthy' in output:
            status = 'false'
        else:
            status = 'true'
    return status


def recreate_container(containers_data):
    """Execute commands included in data to recreate containers.

    Args:
        containers_data (list): informations to recreate containers

    Returns:
        Print status about each step for each container
    """
    for element in containers_data:
        old_ctn_id: str = element[0]
        new_ctn_cli: str = element[1]

        print(f'Recreating container id : {old_ctn_id}')
        print(f'Stopping {old_ctn_id}')
        stop_old = run(['podman', 'stop', old_ctn_id],
                       capture_output=True).stdout.decode('utf-8')
        print(f'Stopping … {stop_old}')

        print('Starting new container …')
        start_new = check_output(f'podman run -d {new_ctn_cli}',
                                 stderr=STDOUT, shell=True).decode('utf-8')
        print(f'Starting … {start_new}')

        healthcheck_status: str = health_check(start_new[:12])
        post_healthcheck(old_ctn_id=old_ctn_id[:12], new_ctn_id=start_new[:12],
                         status=healthcheck_status)

    exitwmsg('Jobs done')


def format_envs_cli(envs_data):
    """Return command line for environment variables.

    Args:
        envs_data (list): from inspect_container

    Returns:
        The command line needed otherwise blank line
    """
    if len(envs_data) > 0:
        added_automatically = ('PATH=', 'TERM=', 'HOSTNAME=', 'container=',
                               'GODEBUG=', 'XDG_CACHE_HOME=', 'HOME=')
        envs_to_remove: List = []
        for prefix in added_automatically:
            envs_to_remove = [env for env in envs_data if prefix in env]
        for env in envs_to_remove:
            envs_data.remove(env)
        return ' '.join([f'-e {env}' for env in envs_data])
    else:
        return ''


def format_network_ports_cli(network_data):
    """Return command line for network ports.

    Args:
        network_data (list): from inspect_container

    Returns:
        The command line needed otherwise blank line
    """
    if len(network_data) > 0:
        network_ports_pre_cli: List[str] = []
        for port in network_data:
            network_ports_pre_cli.append(
                f"""-p {port['hostIP']}:{port['hostPort']}:{
                port['containerPort']}""") if len(
                port['hostIP']) > 0 else network_ports_pre_cli.append(
                f"-p {port['hostPort']}:{port['containerPort']}")
        return ' '.join(network_ports_pre_cli)
    else:
        return ''


def format_mounts_cli(mounts_data):
    """Return command line for mounts.

    Args:
        mounts_data (list): from inspect_container

    Returns:
        The command line needed otherwise blank line
    """
    return ' '.join([f"-v {mount['Source']}:{mount['Destination']}"
                     for mount in mounts_data]) if len(mounts_data) > 0 else ''


def format_restart_cli(restart_data):
    """Return command line for restart policy.

    Args:
        restart_data (list): from inspect_container

    Returns:
        The command line needed otherwise blank line
    """
    return f"--restart={restart_data['Name']}" if len(
        restart_data['Name']) > 0 else ''


def inspect_container(containers_list):
    """Inspect each container and rebuild CLI to recreate each container.

    Args:
        containers_list (list): list of running containers

    Returns:
        List of cli needed to recreate each container
    """
    ctn_to_recreate: List[tuple] = []

    for ctn in containers_list:
        ctn_id = ctn[0]
        print(f'    - {ctn_id} in progress')
        ctn_image = ctn[1]
        inspect_output = run(['podman', 'inspect', '--format', 'json', ctn_id],
                             capture_output=True).stdout.decode('utf-8')
        inspect_json = loads(inspect_output)[0]
        mounts = inspect_json['Mounts']
        network_ports = inspect_json['NetworkSettings']['Ports']
        envs = inspect_json['Config']['Env']
        restart_policy = inspect_json['HostConfig']['RestartPolicy']
        cli_restart_policy = format_restart_cli(restart_policy)
        cli_mounts = format_mounts_cli(mounts)
        cli_network_ports = format_network_ports_cli(network_ports)
        cli_envs = format_envs_cli(envs)
        cli_args = ' '.join(inspect_json['Args'])
        cli = f'{cli_mounts} {cli_envs} {cli_network_ports} ' \
              f'{cli_restart_policy} {ctn_image} {cli_args}'
        ctn_to_recreate.append((ctn_id, cli))
    return ctn_to_recreate


def ctn_img_do(data):
    """Take container list and start the process about inspect and recreate."""
    print('Inspecting running containers:')
    to_recreate_cli: List[tuple] = inspect_container(data)
    recreate_container(to_recreate_cli)


def containers_to_recreate(containers_list, images_updated):
    """Return which containers are to recreate.

    Args:
        containers_list (list): list running containers
        images_updated: (list) updated images

    Returns:
        List of containers needed to be recreated
    """
    return [container for container in containers_list
            if container[1] in images_updated]


def update_img(data):
    """Update image and if updated append it to the list to recreate containers.

    Args:
        data (list): image id, name and tag
    Returns:
        List of images updated
    """
    updated: List = []
    img: tuple

    for img in data:
        print(f'    - {img[1]}')
        pull_output: str = run(
            ['podman', 'pull', '-q', img[1]],
            capture_output=True).stdout.decode('utf-8').rstrip()
        if pull_output != img[0]:
            updated.append(img[1])
    return updated


def identify_img_name_tag(data):
    """Extract image name with tag and append to the list.

    Args:
        data (list): json from podman images
    """
    return [(str(image['id']), image['names'][0]) for image in data
            if image['names'] is not None]


def prepare_containers_list(data):
    """Prepare list used to recreate running container when image is updated.

    Args:
        data (list): json from podman ps
    """
    return [(str(container['ID']), container['Image']) for container in data
            if 'Up' in container['Status']]


def images() -> List[tuple]:
    """Gathering information about images."""
    images_output = run(['podman', 'images', '--format', 'json'],
                        capture_output=True).stdout.decode('utf-8')
    return identify_img_name_tag(loads(images_output))


def ps() -> List[tuple]:
    """Gathering information about running containers."""
    ps_output = run(['podman', 'ps', '--format', 'json'],
                    capture_output=True).stdout.decode('utf-8')
    return prepare_containers_list(loads(ps_output))


def exitwmsg(msg):
    """Avoid duplicate code about printing message and exit program."""
    print(msg)
    exit(0)


def main():
    """Only used when run as a script."""
    print('Gathering information about running containers')
    ctn_list = ps()
    l_ctn_list = len(ctn_list)

    print('Gathering information about images')
    img_id_name_tag = images()

    print('Updating images:')
    img_updated = update_img(img_id_name_tag) if img_id_name_tag else exitwmsg(
        'No image')
    l_img_updated = len(img_updated)
    exitwmsg('No image to update'
             ) if l_img_updated == 0 else print('Images updated')

    ctn_img_do(containers_to_recreate(ctn_list, img_updated)
               ) if l_ctn_list else exitwmsg('No container found')


if __name__ == '__main__':
    main()
