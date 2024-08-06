import os
import pandas as pd


def search_repo_for_task_definitions(base_dir, csv_file, output_file, exclude_dir):
    df = pd.read_csv(csv_file)

    # Add a column for the search results
    df['found_in_repo'] = False

    # Iterate over the rows in the DataFrame
    for index, row in df.iterrows():
        key = row['key']
        found = False

        # Walk through the repo to search for the task definitions excluding the specified directory
        for root, dirs, files in os.walk(base_dir):
            if exclude_dir in root:
                continue
            for file in files:
                if file.endswith('.py') or file.endswith('.json') or file.endswith('.txt'):
                    with open(os.path.join(root, file), 'r', errors='ignore') as f:
                        try:
                            if key in f.read():
                                found = True
                                break
                        except Exception as e:
                            print(f'Error reading file {file}: {e}')
            if found:
                break

        # Update the DataFrame with the search result
        df.at[index, 'found_in_repo'] = found

    # Filter the DataFrame for task definitions not found in the repo
    not_found_df = df[~df['found_in_repo']]

    # Save the result to a new CSV file
    not_found_df.to_csv(output_file, index=False)
    print(f'Search completed. Task definitions not found in the repo have been saved to {output_file}')


if __name__ == '__main__':
    base_dir = './'
    csv_file = './cd/application-deployment/task_definitions.csv'
    output_file = './cd/application-deployment/task_definitions_not_in_use.csv'
    exclude_dir = os.path.join(base_dir, 'cd/application-deployment')
    search_repo_for_task_definitions(base_dir, csv_file, output_file, exclude_dir)
