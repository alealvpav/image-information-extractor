import csv
import os
from full_information import get_exif_dict

images_dir = os.getcwd() + "/images"
images = os.listdir(images_dir)

def get_results_for_dict_writer(images):
    results = []
    for image in images:
        image_path = "images/" + image
        image_info = get_exif_dict(image_path)
        image_info["0-ImageFileName"] = image
        results.append(image_info)
    return results

images_information_for_csv = get_results_for_dict_writer(images=images)

with open("images_geo_information.csv", "w") as csvfile:
    fieldnames = sorted(list(images_information_for_csv[0].keys()))
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    
    writer.writeheader()
    for image_info in images_information_for_csv:
        writer.writerow(image_info)
