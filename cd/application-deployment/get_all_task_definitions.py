import os
import json
import pandas as pd


def extract_task_definitions(base_dir):
    data = []

    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith('-task-definition.json'):
                with open(os.path.join(root, file), 'r') as f:
                    task_def = json.load(f)

                    container_definitions = task_def.get('containerDefinitions', [])
                    for container in container_definitions:
                        container_name = container.get('name')

                        environment = container.get('environment', [])
                        for env in environment:
                            data.append(
                                {
                                    'container': container_name,
                                    'type': 'environment',
                                    'key': env.get('name'),
                                    'value': env.get('value'),
                                }
                            )

                        secrets = container.get('secrets', [])
                        for secret in secrets:
                            data.append(
                                {
                                    'container': container_name,
                                    'type': 'secrets',
                                    'key': secret.get('name'),
                                    'value': secret.get('valueFrom'),
                                }
                            )

    return data


def save_to_csv(data, output_file):
    df = pd.DataFrame(data)
    df.to_csv(output_file, index=False)


if __name__ == '__main__':
    base_dir = './cd/application-deployment'
    output_file = 'task_definitions.csv'
    data = extract_task_definitions(base_dir)
    save_to_csv(data, output_file)
    print(f'Task definitions extracted and saved to {output_file}')
