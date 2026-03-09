import random

# Function to generate a list of random RGB colors
def generate_palette(num_colors=5):
    return [
        (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        for _ in range(num_colors)
    ]

# Print the palette
def print_palette(palette):
    for idx, (r, g, b) in enumerate(palette, 1):
        print(f"\033[48;2;{r};{g};{b}m     \033[0m \033[38;2;{r};{g};{b}mRGB({r}, {g}, {b})\033[0m")

# Generate and print a palette of 5 colors
if __name__ == "__main__":
    while True:
        palette = generate_palette()
        print_palette(palette)
        input("Hit Enter to generate new colors or Ctrl+C to exit...")
