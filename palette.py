import random

def generate_palette(num_colors=5):
    return [
        (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        for _ in range(num_colors)
    ]

def print_palette(palette):
    for idx, (r, g, b) in enumerate(palette, 1):
        hex_value = f"#{r:02X}{g:02X}{b:02X}"
        print(f"\033[48;2;{r};{g};{b}m     \033[0m \033[38;2;{r};{g};{b}m{hex_value} RGB({r}, {g}, {b})\033[0m")

if __name__ == "__main__":
    while True:
        palette = generate_palette()
        print_palette(palette)
        input("Hit Enter to generate new colors or Ctrl+C to exit...")