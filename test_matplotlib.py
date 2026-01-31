from PIL import Image
import numpy as np
from matplotlib.offsetbox import OffsetImage
import matplotlib.pyplot as plt

# Create a dummy image
img = Image.new('RGB', (100, 100), color = 'red')

try:
    oi = OffsetImage(img, zoom=0.1)
    print("OffsetImage accepted PIL Image directly!")
except Exception as e:
    print(f"OffsetImage failed with PIL Image: {e}")

try:
    oi = OffsetImage(np.array(img), zoom=0.1)
    print("OffsetImage accepted NumPy array!")
except Exception as e:
    print(f"OffsetImage failed with NumPy array: {e}")
