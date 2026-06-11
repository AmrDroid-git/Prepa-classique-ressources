[[# Prepa-classique-ressources](https://prepa-resources.netlify.app/

# Prépa Classique Resources
https://prepa-resources.netlify.app/
**Prépa Classique Resources** is a simple community-based website that collects and organizes useful resources for prépa students.  
The goal of the project is to make shared drives, files, and useful websites easier to find from one clean place.

## Project Overview

This project was built around a small data pipeline and a static website:

1. **Collecting data from the community**  
   Resource links were collected from students and community members.

2. **Cleaning and organizing links**  
   The collected links were cleaned, checked, and separated into useful categories.

3. **Labeling Google Drive resources with OpenRouter**  
   Google Drive links were analyzed and labeled using an OpenRouter API key in order to generate clearer names and descriptions.

4. **Dividing the dataset into three parts**  
   The final data was organized into:
   - Websites
   - Google Drive folders
   - Google Drive files

5. **Scraping Google Drive owners**  
   Python scripts were used to scrape and add the owners of the shared Google Drive folders when possible.

6. **Creating the website**  
   The website was created as a static HTML, CSS, and JavaScript project with the help of ChatGPT.

7. **Deployment**  
   The final website was deployed online using Netlify.

## Website Pages

The website contains pages for:

- Home
- Folders
- Files
- Websites
- Download All
- Collaborate
- About

## Data Structure

The website uses JSON files to display resources dynamically:

```txt
data/
├── folders.json
├── files.json
└── websites.json
```

Each page reads the corresponding JSON file and displays the resources as clean cards.

## Tech Used

- HTML
- CSS
- JavaScript
- Python
- JSON
- OpenRouter API
- ChatGPT
- Netlify

## Thanks

Special thanks to:

- ChatGPT
- Amr Slama
- OpenRouter
- El Mostahlek
- El Mostahlkin

## Note

This project is community-driven. The resources are collected to help students access useful educational material more easily.
)](https://prepa-resources.netlify.app/

# Prépa Classique Resources

**Prépa Classique Resources** is a simple community-based website that collects and organizes useful resources for prépa students.  
The goal of the project is to make shared drives, files, and useful websites easier to find from one clean place.

## Project Overview

This project was built around a small data pipeline and a static website:

1. **Collecting data from the community**  
   Resource links were collected from students and community members.

2. **Cleaning and organizing links**  
   The collected links were cleaned, checked, and separated into useful categories.

3. **Labeling Google Drive resources with OpenRouter**  
   Google Drive links were analyzed and labeled using an OpenRouter API key in order to generate clearer names and descriptions.

4. **Dividing the dataset into three parts**  
   The final data was organized into:
   - Websites
   - Google Drive folders
   - Google Drive files

5. **Scraping Google Drive owners**  
   Python scripts were used to scrape and add the owners of the shared Google Drive folders when possible.

6. **Creating the website**  
   The website was created as a static HTML, CSS, and JavaScript project with the help of ChatGPT.

7. **Deployment**  
   The final website was deployed online using Netlify.

## Website Pages

The website contains pages for:

- Home
- Folders
- Files
- Websites
- Download All
- Collaborate
- About

## Data Structure

The website uses JSON files to display resources dynamically:

```txt
data/
├── folders.json
├── files.json
└── websites.json
```

Each page reads the corresponding JSON file and displays the resources as clean cards.

## Tech Used

- HTML
- CSS
- JavaScript
- Python
- JSON
- OpenRouter API
- ChatGPT
- Netlify

## Thanks

Special thanks to:

- ChatGPT
- Amr Slama
- OpenRouter
- El Mostahlek
- El Mostahlkin

## Note

This project is community-driven. The resources are collected to help students access useful educational material more easily.
)
