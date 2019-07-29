import requests, json, arrow, hashlib, urllib, datetime, pickle
from secret import USERNAME, PASSWORD, NS_URL, NS_SECRET, BASAL_TYPE

# this is the enteredBy field saved to Nightscout
NS_AUTHOR = "Diabetes-M"

DO_MYSUGR_PROCESSING = (USERNAME == 'jwoglom')

def get_login():
	return requests.post('https://analytics.diabetes-m.com/api/v1/user/authentication/login', json={
		'username': USERNAME,
		'password': PASSWORD,
		'device': ''
	}, headers={
		'origin': 'https://analytics.diabetes-m.com'
	})


def get_entries(login):
	auth_code = login.json()['token']
	print("Loading entries...")
	entries = requests.post('https://analytics.diabetes-m.com/api/v1/diary/entries/list', 
		cookies=login.cookies, 
		headers={
			'origin': 'https://analytics.diabetes-m.com',
			'authorization': 'Bearer '+auth_code
		}, json={
			'fromDate': -1,
			'toDate': -1,
			'page_count': 90000,
			'page_start_entry_time': 0
		})

	return entries.json()


def to_mgdl(mmol):
	return round(mmol*18)

def convert_nightscout(entries, start_time=None):
	out = []
	with open('data.json', 'w', encoding='utf-8') as f:
		json.dump(entries, f, ensure_ascii=False, indent=4)
	for entry in entries:
		bolus = entry["carb_bolus"] + entry["correction_bolus"]
		time = arrow.get(int(entry["entry_time"])/1000).to(entry["timezone"])
		time2 = arrow.get(int(entry["entry_time"])/1000).isoformat()
		notes = entry["notes"]

		if start_time and start_time >= time:
			continue
		
		author = NS_AUTHOR

		# You can do some custom processing here, if necessary. e.x.:
		if entry["basal"]:
			out.append({
				"eventType": "Temp Basal",
				"created_at": time2.format(),
				"absolute": entry["basal"],
				"enteredBy": author,
				"duration": 1440,
				"reason": BASAL_TYPE,
				"notes": BASAL_TYPE
			})
		if "Night" in notes:
			print ('Entry originated from nightscout'),
			continue

		if entry["medications_list"]:
			out.append({
				notes =  notes + "--pills taken--",
				"eventType": "Note",
				"notes": notes
			
			})

		dat = {
			"eventType": "Meal Bolus",
			"created_at": time2.format(),
			"carbs": entry["carbs"],
			"insulin": bolus,
			"notes": notes,
			"enteredBy": author
		}
		if entry["glucose"]:
			glucose = entry["glucoseInCurrentUnit"] if entry["glucoseInCurrentUnit"] and entry["us_units"] else to_mgdl(entry["glucose"])
			dat.update({
				"eventType": "BG Check",
				"glucose": glucose,
				"glucoseType": "Finger",
				"units": "mg/dL"
			})			

		out.append(dat)

	return out

def upload_nightscout(ns_format):
	upload = requests.post(NS_URL + 'api/v1/treatments?api_secret=' + NS_SECRET, json=ns_format, headers={
		'Accept': 'application/json',
		'Content-Type': 'application/json',
		'api-secret': hashlib.sha1(NS_SECRET.encode()).hexdigest()
	})
	print("Nightscout upload status:", upload.status_code, upload.text)

def get_last_nightscout():
	last = requests.get(NS_URL + 'api/v1/treatments?count=1&find[enteredBy]='+urllib.parse.quote(NS_AUTHOR))
	if last.status_code == 200:
		js = last.json()
		if len(js) > 0:
			return arrow.get(js[0]['created_at']).datetime

def main():
	print("Logging in to Diabetes-M...", datetime.datetime.now())
	login = get_login()
	if login.status_code == 200:
		entries = get_entries(login)
	else:
		print("Error logging in to Diabetes-M: ",login.status_code, login.text)
		exit(0)

	print("Loaded", len(entries["logEntryList"]), "entries")

	# skip uploading entries past the last entry
	# uploaded to Nightscout by `NS_AUTHOR`
	ns_last = get_last_nightscout()

	ns_format = convert_nightscout(entries["logEntryList"], ns_last)

	print("Converted", len(ns_format), "entries to Nightscout format")
	print(ns_format)

	print("Uploading", len(ns_format), "entries to Nightscout...")
	upload_nightscout(ns_format)


if __name__ == '__main__':
	main()

