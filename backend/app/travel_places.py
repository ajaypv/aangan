"""Curated sample places to visit and restaurants for the Family Room planner (source is always "sample").

Places are real landmarks with approximate coordinates and rough, rounded entry prices; restaurants are invented
names placed in real neighbourhoods, with typical prices. This is reference data for a demo, not a live listing, and
the planner labels it that way. Every place and restaurant records what a family needs to know: step-free access
for places, and vegetarian availability for restaurants, so household memory (a grandmother with bad knees, a pure
vegetarian, a peanut allergy) can steer what gets proposed.
"""

import hashlib

from . import travel_data

# name, area, category, lat, lon, duration_min, price per person in rupees, step_free, note
_PLACES: dict[str, list[tuple]] = {
    "Goa": [
        ("Basilica of Bom Jesus", "Old Goa", "sight", 15.5009, 73.9116, 60, 0, True, "Ramp at the side entrance"),
        ("Fort Aguada", "Candolim", "sight", 15.4925, 73.7736, 75, 25, False, "Steep climb to the lighthouse, sunset views"),
        ("Baga Beach", "Baga", "beach", 15.5553, 73.7517, 120, 0, False, "Busy, soft sand; water sports available"),
        ("Anjuna Flea Market", "Anjuna", "market", 15.5736, 73.7410, 120, 0, False, "Wednesdays only, crowded"),
        ("Fontainhas Latin Quarter", "Panaji", "sight", 15.4989, 73.8333, 90, 0, True, "Flat, shaded lanes and painted houses"),
        ("Dudhsagar Falls", "Mollem", "nature", 15.3144, 74.3143, 300, 900, False, "Jeep ride and a short walk; a long day"),
        ("Chapora Fort", "Vagator", "sight", 15.6063, 73.7358, 60, 0, False, "Uneven stone steps"),
        ("Mangueshi Temple", "Ponda", "temple", 15.4486, 73.9714, 45, 0, True, "Level courtyard"),
        ("Palolem Beach", "Canacona", "beach", 15.0100, 74.0232, 150, 0, False, "Calm crescent bay, far south"),
        ("Sahakari Spice Plantation", "Ponda", "activity", 15.4030, 74.0210, 150, 500, True, "Guided walk and a Goan lunch included"),
        ("Mandovi Sunset Cruise", "Panaji", "activity", 15.5000, 73.8210, 60, 400, True, "Boat with live folk music; step-free jetty"),
    ],
    "Mumbai": [
        ("Gateway of India", "Colaba", "sight", 18.9220, 72.8347, 45, 0, True, "Open waterfront promenade"),
        ("Marine Drive", "Churchgate", "sight", 18.9440, 72.8230, 60, 0, True, "Flat seafront walk, best at sunset"),
        ("Elephanta Caves", "Elephanta Island", "sight", 18.9633, 72.9315, 240, 250, False, "Ferry plus 120 steps to the caves"),
        ("Chhatrapati Shivaji Terminus", "Fort", "sight", 18.9398, 72.8355, 30, 0, True, "Heritage railway station, view from outside"),
        ("Juhu Beach", "Juhu", "beach", 19.0988, 72.8266, 90, 0, False, "Street food stalls at dusk"),
        ("Sanjay Gandhi National Park", "Borivali", "nature", 19.2147, 72.9106, 180, 80, False, "Kanheri caves trail is steep"),
        ("Crawford Market", "Fort", "market", 18.9473, 72.8342, 75, 0, False, "Crowded and narrow aisles"),
        ("Siddhivinayak Temple", "Prabhadevi", "temple", 19.0169, 72.8302, 60, 0, True, "Queues can be long on Tuesdays"),
        ("Haji Ali Dargah", "Worli", "temple", 18.9827, 72.8089, 60, 0, False, "Causeway is walked at low tide"),
        ("Kala Ghoda Art Walk", "Kala Ghoda", "food_walk", 18.9283, 72.8312, 90, 0, True, "Galleries and cafes on level pavements"),
    ],
    "Delhi": [
        ("Red Fort", "Old Delhi", "sight", 28.6562, 77.2410, 120, 35, True, "Wide paved paths; wheelchairs allowed"),
        ("India Gate", "Rajpath", "sight", 28.6129, 77.2295, 60, 0, True, "Lawns and promenade, lovely in the evening"),
        ("Qutub Minar", "Mehrauli", "sight", 28.5245, 77.1855, 90, 35, False, "Uneven ground around the ruins"),
        ("Humayun's Tomb", "Nizamuddin", "sight", 28.5933, 77.2507, 90, 35, True, "Level gardens, ramps at the tomb"),
        ("Lotus Temple", "Kalkaji", "temple", 28.5535, 77.2588, 60, 0, True, "Quiet, free entry"),
        ("Akshardham Temple", "Noida Mor", "temple", 28.6127, 77.2773, 180, 0, True, "No phones or bags inside; step-free"),
        ("Chandni Chowk food walk", "Old Delhi", "food_walk", 28.6506, 77.2303, 150, 0, False, "Very crowded lanes; best by rickshaw"),
        ("Jama Masjid", "Old Delhi", "temple", 28.6507, 77.2334, 60, 0, False, "Steep stairs at the gates"),
        ("Dilli Haat", "INA", "market", 28.5738, 77.2090, 90, 30, True, "Crafts and regional food stalls, level paths"),
        ("Lodhi Garden", "Lodhi Colony", "nature", 28.5918, 77.2197, 60, 0, True, "Flat paths and benches"),
    ],
    "Jaipur": [
        ("Amber Fort", "Amer", "sight", 26.9855, 75.8513, 150, 100, False, "Steep slope; jeeps run to the top"),
        ("City Palace", "Old City", "sight", 26.9258, 75.8237, 120, 200, True, "Ground-floor courtyards are level"),
        ("Hawa Mahal", "Old City", "sight", 26.9239, 75.8267, 45, 50, False, "Best photographed from the street opposite"),
        ("Jantar Mantar", "Old City", "sight", 26.9247, 75.8246, 60, 50, True, "Open-air observatory, flat"),
        ("Nahargarh Fort", "Nahargarh Hills", "sight", 26.9373, 75.8155, 90, 50, False, "Sunset viewpoint, uneven"),
        ("Jal Mahal", "Man Sagar Lake", "sight", 26.9535, 75.8466, 30, 0, True, "Lake-side promenade"),
        ("Johari Bazaar", "Old City", "market", 26.9190, 75.8280, 90, 0, False, "Jewellery and textiles, crowded"),
        ("Albert Hall Museum", "Ram Niwas Garden", "sight", 26.9118, 75.8195, 75, 40, True, "Lift and ramps"),
        ("Chokhi Dhani village evening", "Tonk Road", "activity", 26.7715, 75.8450, 180, 800, True, "Folk dance and a Rajasthani thali dinner"),
    ],
    "Kochi": [
        ("Chinese fishing nets", "Fort Kochi", "sight", 9.9658, 76.2421, 45, 0, True, "Seafront promenade"),
        ("Mattancherry Palace", "Mattancherry", "sight", 9.9578, 76.2597, 60, 5, False, "Steps at the entrance"),
        ("Jew Town and Paradesi Synagogue", "Mattancherry", "market", 9.9570, 76.2593, 75, 10, True, "Antiques and spice shops"),
        ("Marine Drive Kochi", "Ernakulam", "sight", 9.9816, 76.2756, 60, 0, True, "Flat backwater promenade"),
        ("Kathakali performance", "Fort Kochi", "activity", 9.9690, 76.2430, 90, 350, True, "Watch the make-up before the show"),
        ("Alleppey backwater houseboat", "Alappuzha", "nature", 9.4981, 76.3388, 360, 2500, True, "Day cruise with a Kerala lunch"),
        ("Eravikulam National Park", "Munnar", "nature", 10.1950, 77.0600, 240, 200, False, "Hill walk to see the Nilgiri tahr"),
        ("Cherai Beach", "Cherai", "beach", 10.1403, 76.1783, 120, 0, False, "Quiet beach with backwater views"),
        ("Athirappilly Waterfalls", "Thrissur", "nature", 10.2850, 76.5700, 240, 100, False, "Viewpoint is a short walk"),
        ("Hill Palace Museum", "Tripunithura", "sight", 9.9490, 76.3490, 90, 30, True, "Level grounds"),
    ],
    "Hyderabad": [
        ("Charminar", "Old City", "sight", 17.3616, 78.4747, 60, 25, False, "Narrow stairs; bazaar around it is crowded"),
        ("Golconda Fort", "Golconda", "sight", 17.3833, 78.4011, 150, 25, False, "Hundreds of steps to the top"),
        ("Hussain Sagar and Buddha statue", "Necklace Road", "nature", 17.4239, 78.4738, 60, 0, True, "Lakeside promenade"),
        ("Salar Jung Museum", "Darulshifa", "sight", 17.3713, 78.4804, 120, 20, True, "Lifts and ramps"),
        ("Chowmahalla Palace", "Old City", "sight", 17.3578, 78.4717, 90, 80, True, "Large level courtyards"),
        ("Ramoji Film City", "Abdullapurmet", "activity", 17.2543, 78.6808, 360, 1500, True, "Full-day park with trams between sets"),
        ("Laad Bazaar bangles", "Old City", "market", 17.3604, 78.4735, 75, 0, False, "Crowded lane beside Charminar"),
        ("Shilparamam crafts village", "Madhapur", "market", 17.4513, 78.3820, 90, 50, True, "Open-air craft stalls"),
    ],
    "Chennai": [
        ("Marina Beach", "Marina", "beach", 13.0500, 80.2824, 90, 0, True, "Paved promenade along the sand"),
        ("Kapaleeshwarar Temple", "Mylapore", "temple", 13.0337, 80.2698, 60, 0, True, "Dress modestly; level courtyard"),
        ("Fort St. George Museum", "Fort", "sight", 13.0794, 80.2875, 75, 25, True, "Ground-floor galleries"),
        ("San Thome Basilica", "Mylapore", "sight", 13.0338, 80.2785, 45, 0, True, "Level entrance"),
        ("Government Museum", "Egmore", "sight", 13.0714, 80.2563, 90, 50, True, "Bronze gallery is a highlight"),
        ("Mahabalipuram Shore Temple", "Mahabalipuram", "sight", 12.6168, 80.1992, 120, 40, False, "An hour south by road; uneven rock"),
        ("Elliot's Beach", "Besant Nagar", "beach", 13.0003, 80.2711, 90, 0, False, "Cafes along the road"),
        ("DakshinaChitra", "Muttukadu", "activity", 12.8244, 80.2408, 150, 150, True, "Living museum of southern crafts"),
    ],
    "Bengaluru": [
        ("Lalbagh Botanical Garden", "Lalbagh", "nature", 12.9507, 77.5848, 90, 30, True, "Paved loops and a glass house"),
        ("Cubbon Park", "Kasturba Road", "nature", 12.9763, 77.5929, 60, 0, True, "Shaded level paths"),
        ("Bangalore Palace", "Vasanth Nagar", "sight", 12.9988, 77.5921, 90, 270, True, "Audio guide included"),
        ("Vidhana Soudha", "Ambedkar Veedhi", "sight", 12.9795, 77.5907, 20, 0, True, "View from the road"),
        ("ISKCON Temple", "Rajajinagar", "temple", 13.0098, 77.5511, 75, 0, True, "Lifts to the main hall"),
        ("Tipu Sultan's Summer Palace", "Chamarajpet", "sight", 12.9593, 77.5738, 45, 25, False, "Steps to the upper floor"),
        ("Commercial Street", "Shivajinagar", "market", 12.9822, 77.6082, 90, 0, True, "Clothes and jewellery, level pavements"),
        ("VV Puram Food Street", "Basavanagudi", "food_walk", 12.9437, 77.5731, 90, 0, False, "Evenings only, crowded"),
        ("Nandi Hills sunrise", "Chikkaballapur", "nature", 13.3702, 77.6835, 240, 50, False, "Two hours out of the city, steep roads"),
    ],
    "Manali": [
        ("Hadimba Devi Temple", "Manali", "temple", 32.2480, 77.1800, 60, 0, False, "Forest path with steps"),
        ("Solang Valley", "Solang", "activity", 32.3166, 77.1566, 240, 1500, False, "Ropeway, paragliding and snow play"),
        ("Rohtang Pass", "Rohtang", "nature", 32.3716, 77.2466, 360, 1500, False, "Permit needed; high altitude"),
        ("Old Manali cafes", "Old Manali", "market", 32.2557, 77.1795, 120, 0, False, "Slopes and stairs between cafes"),
        ("Vashisht Hot Springs", "Vashisht", "sight", 32.2680, 77.1873, 75, 0, False, "Village lanes uphill"),
        ("Mall Road stroll", "Manali", "market", 32.2432, 77.1892, 90, 0, True, "Pedestrian street"),
    ],
    "Ooty": [
        ("Ooty Lake and boat house", "Ooty", "nature", 11.4082, 76.6890, 90, 20, True, "Paved lakeside, pedal boats"),
        ("Government Botanical Garden", "Ooty", "nature", 11.4180, 76.7108, 90, 50, False, "Terraced slopes"),
        ("Doddabetta Peak", "Doddabetta", "nature", 11.4000, 76.7350, 60, 20, True, "Road goes close to the viewpoint"),
        ("Nilgiri Mountain Railway ride", "Ooty", "activity", 11.4064, 76.6958, 180, 300, True, "Toy train to Coonoor, book ahead"),
        ("Tea factory and museum", "Ooty", "activity", 11.4090, 76.7180, 60, 30, True, "Short tour and tea tasting"),
        ("Pykara Falls", "Pykara", "nature", 11.4400, 76.5900, 90, 0, False, "Short walk down steps"),
    ],
    "Udaipur": [
        ("City Palace Udaipur", "Lake Pichola", "sight", 24.5764, 73.6835, 120, 300, False, "Many levels and stairs inside"),
        ("Lake Pichola boat ride", "Lake Pichola", "activity", 24.5726, 73.6790, 60, 400, True, "Sunset boat from Bansi Ghat"),
        ("Jagdish Temple", "Old City", "temple", 24.5786, 73.6836, 30, 0, False, "Steep steps at the entrance"),
        ("Saheliyon-ki-Bari", "Fatehpura", "nature", 24.6000, 73.6900, 60, 50, True, "Fountain gardens, level paths"),
        ("Sajjangarh Monsoon Palace", "Sajjangarh", "sight", 24.5942, 73.6545, 90, 120, False, "Hilltop sunset viewpoint"),
        ("Fateh Sagar Lake", "Fatehpura", "nature", 24.6000, 73.6720, 60, 0, True, "Lakeside walk and snack stalls"),
        ("Bagore Ki Haveli", "Gangaur Ghat", "sight", 24.5791, 73.6803, 60, 100, False, "Evening dance show"),
    ],
}

# neighbourhood centres, so a restaurant's map pin lands in the right area
_AREAS: dict[str, dict[str, tuple[float, float]]] = {
    "Goa": {"Assagao": (15.5920, 73.7640), "Panaji": (15.4989, 73.8300), "Candolim": (15.5183, 73.7620), "Calangute": (15.5440, 73.7550),
            "Baga": (15.5553, 73.7517), "Old Goa": (15.5009, 73.9116), "Palolem": (15.0100, 74.0232), "Vagator": (15.6030, 73.7390)},
    "Mumbai": {"Colaba": (18.9220, 72.8330), "Bandra": (19.0596, 72.8295), "Churchgate": (18.9322, 72.8264), "Juhu": (19.1075, 72.8263),
               "Fort": (18.9340, 72.8350), "Matunga": (19.0270, 72.8570)},
    "Delhi": {"Connaught Place": (28.6315, 77.2167), "Old Delhi": (28.6506, 77.2303), "Hauz Khas": (28.5494, 77.2001),
              "Khan Market": (28.6000, 77.2270), "Nizamuddin": (28.5880, 77.2450), "Karol Bagh": (28.6519, 77.1909)},
    "Jaipur": {"MI Road": (26.9150, 75.8050), "Bani Park": (26.9330, 75.7900), "Johari Bazaar": (26.9190, 75.8280),
               "C-Scheme": (26.9124, 75.7960), "Amer": (26.9855, 75.8513), "Vaishali Nagar": (26.9100, 75.7430)},
    "Kochi": {"Fort Kochi": (9.9658, 76.2421), "Marine Drive": (9.9816, 76.2756), "Mattancherry": (9.9578, 76.2597),
              "MG Road": (9.9680, 76.2900), "Alappuzha": (9.4981, 76.3388), "Edappally": (10.0261, 76.3080)},
    "Hyderabad": {"Banjara Hills": (17.4126, 78.4482), "Old City": (17.3616, 78.4747), "Jubilee Hills": (17.4326, 78.4071),
                  "Hitech City": (17.4435, 78.3772), "Begumpet": (17.4440, 78.4690), "Abids": (17.3920, 78.4770)},
    "Chennai": {"Mylapore": (13.0339, 80.2693), "T Nagar": (13.0418, 80.2341), "Egmore": (13.0732, 80.2609),
                "Adyar": (13.0067, 80.2570), "Nungambakkam": (13.0600, 80.2420)},
    "Bengaluru": {"Indiranagar": (12.9784, 77.6408), "Koramangala": (12.9352, 77.6245), "Basavanagudi": (12.9422, 77.5740),
                  "MG Road": (12.9756, 77.6068), "Malleshwaram": (13.0035, 77.5700), "Jayanagar": (12.9250, 77.5938)},
    "Manali": {"Mall Road": (32.2432, 77.1892), "Old Manali": (32.2557, 77.1795), "Aleo": (32.2650, 77.1750)},
    "Ooty": {"Charing Cross": (11.4100, 76.6950), "Coonoor Road": (11.4000, 76.7000), "Lake Road": (11.4082, 76.6890)},
    "Udaipur": {"Lake Pichola": (24.5726, 73.6790), "Hanuman Ghat": (24.5790, 73.6810), "Fatehpura": (24.5950, 73.6750),
                "Chandpole": (24.5800, 73.6870)},
}

# name, cuisine, area, meals served, price for two in rupees, veg ("only" | "opt" | "no"), note
_RESTAURANTS: dict[str, list[tuple]] = {
    "Goa": [
        ("Sea Salt Shack", "Goan seafood", "Baga", "lunch,dinner", 1800, "opt", "Fish curry and prawn balchao; vegetarian dishes on request"),
        ("Assagao Spice Kitchen", "Goan", "Assagao", "lunch,dinner", 1100, "opt", "Xacuti and sannas; check the sauces for nuts"),
        ("Panjim Udupi Bhojan", "South Indian", "Panaji", "breakfast,lunch", 500, "only", "Dosa, idli and meals on a banana leaf"),
        ("Candolim Pure Veg Thali House", "Gujarati thali", "Candolim", "lunch,dinner", 700, "only", "Unlimited thali, early dinner service"),
        ("Beachside Cafe Calangute", "Cafe and continental", "Calangute", "breakfast,snack", 900, "opt", "Pancakes, fresh juices and sea views"),
        ("Old Goa Heritage Dine", "Goan Portuguese", "Old Goa", "dinner", 2200, "opt", "Candlelit courtyard, book ahead"),
        ("Vagator Cliff Kitchen", "Mediterranean", "Vagator", "dinner", 2400, "opt", "Sunset seating"),
    ],
    "Mumbai": [
        ("Colaba Irani Cafe", "Irani cafe", "Colaba", "breakfast,snack", 400, "opt", "Bun maska and chai, old-school"),
        ("Churchgate Veg Bhojanalaya", "Gujarati and Maharashtrian", "Churchgate", "lunch,dinner", 800, "only", "Thali lunch, quick service"),
        ("Bandra Bay Seafood", "Coastal seafood", "Bandra", "lunch,dinner", 2200, "opt", "Bombay duck and surmai fry"),
        ("Juhu Chowpatty Chaat Corner", "Street food", "Juhu", "snack,dinner", 350, "only", "Pav bhaji and bhel by the beach"),
        ("Fort Parsi Dining Room", "Parsi", "Fort", "lunch", 1300, "opt", "Dhansak and caramel custard"),
        ("Matunga South Indian Mess", "South Indian", "Matunga", "breakfast,lunch", 450, "only", "Filter coffee and crisp dosas"),
        ("Colaba Rooftop Grill", "Continental", "Colaba", "dinner", 2800, "opt", "Harbour view, ramp access from the lobby"),
    ],
    "Delhi": [
        ("Old Delhi Paratha House", "North Indian", "Old Delhi", "breakfast,lunch", 450, "only", "Stuffed parathas and lassi"),
        ("Connaught Tandoor Room", "Mughlai", "Connaught Place", "lunch,dinner", 2000, "opt", "Kebabs and butter chicken; paneer options"),
        ("Hauz Khas Rooftop Cafe", "Cafe and continental", "Hauz Khas", "breakfast,dinner", 1600, "opt", "Lake and ruins view"),
        ("Khan Market Pure Veg Kitchen", "North Indian", "Khan Market", "lunch,dinner", 1200, "only", "Dal makhani and chole bhature"),
        ("Nizamuddin Kebab Corner", "Mughlai", "Nizamuddin", "dinner", 900, "no", "Near the dargah, busy after sunset"),
        ("Karol Bagh Chaat Stop", "Street food", "Karol Bagh", "snack", 300, "only", "Golgappa and aloo tikki"),
        ("Delhi Thali Haveli", "Rajasthani and Punjabi thali", "Connaught Place", "lunch,dinner", 1100, "only", "Step-free entrance, early dinner"),
    ],
    "Jaipur": [
        ("Johari Rasoi", "Rajasthani thali", "Johari Bazaar", "lunch,dinner", 750, "only", "Dal baati churma and gatte ki sabzi"),
        ("Bani Park Courtyard Kitchen", "Rajasthani", "Bani Park", "lunch,dinner", 1400, "opt", "Laal maas for the non-vegetarians"),
        ("MI Road Lassi and Kachori", "Snacks", "MI Road", "breakfast,snack", 250, "only", "Pyaaz kachori and lassi in clay cups"),
        ("Amer View Terrace", "North Indian", "Amer", "lunch", 1500, "opt", "Fort views from the terrace"),
        ("C-Scheme Cafe Bistro", "Cafe and continental", "C-Scheme", "breakfast,dinner", 1700, "opt", "Quiet, air conditioned, step-free"),
        ("Vaishali Nagar Pure Veg Dhaba", "Punjabi dhaba", "Vaishali Nagar", "lunch,dinner", 650, "only", "Large family tables"),
        ("Palace Road Royal Dining", "Royal Rajasthani", "MI Road", "dinner", 3200, "opt", "Live folk music, book ahead"),
    ],
    "Kochi": [
        ("Fort Kochi Seafood Shack", "Kerala seafood", "Fort Kochi", "lunch,dinner", 1400, "opt", "Karimeen pollichathu, pick your fish"),
        ("Mattancherry Appam House", "Kerala breakfast", "Mattancherry", "breakfast", 350, "opt", "Appam, stew and puttu"),
        ("MG Road Sadya Hall", "Kerala sadya", "MG Road", "lunch", 600, "only", "Banana leaf meal, vegetarian only"),
        ("Marine Drive Waterfront Cafe", "Cafe", "Marine Drive", "snack,dinner", 1300, "opt", "Evening breeze, step-free"),
        ("Alappuzha Toddy Shop Kitchen", "Kerala home style", "Alappuzha", "lunch", 800, "opt", "Beef and fish fry, vegetarian thoran too"),
        ("Edappally Veg Meals", "South Indian", "Edappally", "breakfast,lunch", 400, "only", "Quick, clean and cheap"),
        ("Fort Kochi Heritage Dining", "Continental and Kerala", "Fort Kochi", "dinner", 2600, "opt", "Old Dutch house, garden seating"),
    ],
    "Hyderabad": [
        ("Charminar Biryani House", "Hyderabadi", "Old City", "lunch,dinner", 900, "no", "Dum biryani; ask for the vegetable biryani variant"),
        ("Banjara Hills Pure Veg Tiffins", "South Indian", "Banjara Hills", "breakfast,lunch", 450, "only", "Pesarattu and idli"),
        ("Jubilee Hills Andhra Meals", "Andhra", "Jubilee Hills", "lunch,dinner", 1000, "opt", "Very spicy; ask for mild"),
        ("Hitech City Rooftop Grill", "Continental", "Hitech City", "dinner", 2200, "opt", "City lights, lift access"),
        ("Begumpet Irani Chai", "Irani cafe", "Begumpet", "breakfast,snack", 250, "opt", "Osmania biscuits and chai"),
        ("Abids Mithai and Chaat", "Sweets and chaat", "Abids", "snack", 300, "only", "Double ka meetha and qubani"),
    ],
    "Chennai": [
        ("Mylapore Tiffin Room", "South Indian", "Mylapore", "breakfast,lunch", 400, "only", "Filter coffee and ven pongal"),
        ("T Nagar Meals Mess", "Tamil meals", "T Nagar", "lunch", 450, "only", "Unlimited banana leaf meals"),
        ("Adyar Chettinad Kitchen", "Chettinad", "Adyar", "lunch,dinner", 1300, "opt", "Fiery; vegetarian chettinad dishes available"),
        ("Egmore Biryani and Kebabs", "Mughlai", "Egmore", "dinner", 900, "no", "Close to the station"),
        ("Nungambakkam Garden Cafe", "Cafe and continental", "Nungambakkam", "breakfast,snack", 1100, "opt", "Quiet garden, step-free"),
    ],
    "Bengaluru": [
        ("Basavanagudi Dosa Camp", "South Indian", "Basavanagudi", "breakfast", 350, "only", "Benne dosa and filter coffee, queues at weekends"),
        ("Koramangala Craft Kitchen", "Modern Indian", "Koramangala", "lunch,dinner", 1800, "opt", "Busy brewery crowd"),
        ("Indiranagar Rooftop Bistro", "Continental", "Indiranagar", "dinner", 2300, "opt", "Lift to the terrace"),
        ("Jayanagar Meals Hotel", "Karnataka meals", "Jayanagar", "lunch,dinner", 550, "only", "Ragi mudde and bisi bele bath"),
        ("MG Road Cafe Express", "Cafe", "MG Road", "breakfast,snack", 900, "opt", "Sandwiches and cold coffee"),
        ("Malleshwaram Military Hotel", "Karnataka non-veg", "Malleshwaram", "lunch,dinner", 800, "no", "Pepper chicken and ghee rice"),
    ],
    "Manali": [
        ("Mall Road Tibetan Kitchen", "Tibetan", "Mall Road", "lunch,dinner", 800, "opt", "Momos and thukpa"),
        ("Old Manali River Cafe", "Cafe", "Old Manali", "breakfast,snack", 700, "opt", "Trout and pancakes by the river"),
        ("Aleo Himachali Dham", "Himachali", "Aleo", "lunch", 650, "opt", "Traditional dham meal"),
        ("Manali Pure Veg Dhaba", "North Indian", "Mall Road", "lunch,dinner", 600, "only", "Hot rotis and rajma chawal"),
    ],
    "Ooty": [
        ("Charing Cross Tea Room", "Cafe", "Charing Cross", "breakfast,snack", 500, "opt", "Homemade chocolates and Nilgiri tea"),
        ("Ooty Meals Hotel", "South Indian", "Lake Road", "lunch,dinner", 550, "only", "Simple vegetarian meals"),
        ("Coonoor Road Kitchen", "Multi cuisine", "Coonoor Road", "lunch,dinner", 1200, "opt", "Warm fireplace seating"),
        ("Lake Road Bakery", "Bakery", "Lake Road", "breakfast,snack", 400, "opt", "Fresh cakes and varkey"),
    ],
    "Udaipur": [
        ("Lake View Rooftop", "Rajasthani and continental", "Lake Pichola", "dinner", 2400, "opt", "Palace views, stairs to the roof"),
        ("Hanuman Ghat Thali House", "Rajasthani thali", "Hanuman Ghat", "lunch,dinner", 700, "only", "Steady crowd of families"),
        ("Fatehpura Garden Cafe", "Cafe", "Fatehpura", "breakfast,snack", 900, "opt", "Step-free garden seating"),
        ("Chandpole Mewari Kitchen", "Mewari", "Chandpole", "lunch,dinner", 1100, "opt", "Local recipes with ghee"),
    ],
}

PLACE_CATEGORIES = ("sight", "beach", "market", "temple", "nature", "activity", "food_walk", "other")
MEALS = ("breakfast", "lunch", "dinner", "snack")
COVERED_CITIES = tuple(_PLACES)


def _jitter(name: str, span: float = 0.0035) -> tuple[float, float]:
    """A small stable offset, so two restaurants in one neighbourhood do not sit on the same map pin."""
    digest = hashlib.sha1(name.encode()).digest()
    return ((digest[0] / 255 - 0.5) * span, (digest[1] / 255 - 0.5) * span)


def _city_name(city_name: str) -> str | None:
    found = travel_data.city(city_name)
    return found["name"] if found and found["name"] in _PLACES else None


def covers(city_name: str) -> bool:
    return _city_name(city_name) is not None


def sample_places(city_name: str, interests: list[str] | None = None, step_free_first: bool = False, limit: int = 8) -> list[dict]:
    """Sample places for a city. `interests` are words such as beach, temple, food or kids: a place that matches any
    (in its category, name or note) is ranked first. With `step_free_first`, step-free places lead the list."""
    name = _city_name(city_name)
    if not name:
        return []
    wanted = [w.lower() for w in (interests or []) if w]
    rows = []
    for n, area, cat, lat, lon, dur, price, step, note in _PLACES[name]:
        place = {
            "name": n, "area": area, "category": cat, "lat": lat, "lon": lon, "duration_min": dur, "price": price, "per": "person",
            "day": None, "notes": note, "source": "sample", "status": "proposed", "step_free": step,
        }
        hay = f"{cat} {n} {note}".lower().replace("_", " ")
        rows.append((place, sum(1 for w in wanted if w in hay or (w == "food" and "food" in cat))))
    rows.sort(key=lambda r: (-r[1], 0 if (r[0]["step_free"] or not step_free_first) else 1, r[0]["price"]))
    return [p for p, _ in rows][:limit]


def sample_restaurants(city_name: str, meal: str | None = None, budget_for_two: int | None = None,
                       veg_only: bool = False, limit: int = 6) -> list[dict]:
    """Sample restaurants for a city that serve `meal`, within a budget for two, vegetarian-only on request."""
    name = _city_name(city_name)
    if not name:
        return []
    out = []
    for n, cuisine, area, meals, price, veg, note in _RESTAURANTS[name]:
        served = meals.split(",")
        if meal and meal not in served:
            continue
        if veg_only and veg == "no":
            continue
        if budget_for_two and price > budget_for_two:
            continue
        base = _AREAS[name].get(area, (travel_data.city(name)["lat"], travel_data.city(name)["lon"]))
        dlat, dlon = _jitter(n)
        out.append(
            {
                "name": n, "cuisine": cuisine, "area": area, "meal": meal or served[0], "day": None, "date": None, "time": None,
                "price_for_two": price, "veg_only": veg == "only", "veg_options": veg != "no",
                "lat": round(base[0] + dlat, 4), "lon": round(base[1] + dlon, 4), "notes": note, "source": "sample", "status": "proposed",
            }
        )
    # vegetarian-only places first when the family asks for vegetarian, then best value
    out.sort(key=lambda r: (0 if (veg_only and r["veg_only"]) else 1, r["price_for_two"]))
    return out[:limit]
