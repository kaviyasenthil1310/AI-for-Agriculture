ADVISORY_DB = {
    "Healthy": {
        "symptoms": "No visible disease symptoms.",
        "treatment": [
            "Continue regular watering and fertilization.",
            "Monitor plants weekly for early signs of stress.",
        ],
        "prevention": [
            "Maintain proper spacing for airflow.",
            "Use balanced fertilizers and avoid overwatering.",
        ],
    },
    "Early Blight": {
        "symptoms": [
            "Dark brown spots with concentric rings on older leaves.",
            "Yellowing around lesions, leaf drop in severe cases.",
        ],
        "treatment": [
            "Remove and destroy infected leaves.",
            "Apply fungicide containing chlorothalonil or mancozeb as per label.",
            "Avoid overhead irrigation.",
        ],
        "prevention": [
            "Use disease-free seeds and resistant varieties.",
            "Practice crop rotation (2–3 years).",
            "Keep foliage dry; water at the base.",
        ],
    },
    "Late Blight": {
        "symptoms": [
            "Water-soaked lesions turning brown/black.",
            "White fungal growth on leaf undersides in humid conditions.",
        ],
        "treatment": [
            "Apply systemic fungicides (e.g., metalaxyl-based) early.",
            "Remove severely infected plants to reduce spread.",
        ],
        "prevention": [
            "Ensure good drainage and airflow.",
            "Avoid working with wet plants.",
        ],
    },
    "Leaf Spot": {
        "symptoms": [
            "Small circular spots with dark margins.",
            "Spots may merge, causing large necrotic areas.",
        ],
        "treatment": [
            "Prune affected leaves and improve air circulation.",
            "Use copper-based fungicides if severe.",
        ],
        "prevention": [
            "Avoid leaf wetness; water early in the day.",
            "Clean tools between plants.",
        ],
    },
    "Bacterial Wilt": {
        "symptoms": [
            "Sudden wilting of leaves while still green.",
            "Yellowing and stunted growth.",
        ],
        "treatment": [
            "No effective chemical cure; remove infected plants.",
            "Disinfect tools and avoid replanting same crop immediately.",
        ],
        "prevention": [
            "Use resistant varieties if available.",
            "Control insect vectors and practice crop rotation.",
        ],
    },
}

def get_advisory(disease: str) -> dict:
    data = ADVISORY_DB.get(disease, ADVISORY_DB["Healthy"])
    return {
        "disease": disease,
        "symptoms": data["symptoms"],
        "treatment": data["treatment"],
        "prevention": data["prevention"],
    }