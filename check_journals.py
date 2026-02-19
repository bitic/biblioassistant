import requests
import json

ids = "S204847658|S37844757|S93121129|S55737203|S32061424|S70708404|S137773608|S183584863|S64187185|S48977010|S4210188283|S4387286383|S196734849|S141808269|S17729819|S80591372|S86852077"
id_list = ids.split('|')

# Additional journals to check by ISSN
issns = ["3054-1786"]

print(f"Resolving {len(id_list)} journals by ID and {len(issns)} by ISSN...")

for source_id in id_list:
    url = f"https://api.openalex.org/sources/{source_id}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(f"- {data.get('display_name')} ({source_id})")
        else:
            print(f"- Error resolving {source_id}: {response.status_code}")
    except Exception as e:
        print(f"- Exception for {source_id}: {e}")

for issn in issns:
    url = f"https://api.openalex.org/sources/issn:{issn}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(f"- {data.get('display_name')} (ISSN: {issn})")
        else:
            print(f"- {issn}: Not yet indexed in OpenAlex (Status: {response.status_code})")
    except Exception as e:
        print(f"- Exception for {issn}: {e}")
