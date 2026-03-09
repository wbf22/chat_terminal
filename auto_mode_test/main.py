# This script prints out some common ANSI escape code commands with their functions

# Reset
print('\033[0m')  # Resets all attributes

# Text styles
print('\033[1mHello')  # Bold
print('\033[3mHello')  # Italic
print('\033[4mHello')  # Underline

# Text colors
print('\033[30mBlack')  # Black
print('\033[31mRed')  # Red
print('\033[32mGreen')  # Green
print('\033[33mYellow')  # Yellow
print('\033[34mBlue')  # Blue
print('\033[35mMagenta')  # Magenta
print('\033[36mCyan')  # Cyan
print('\033[37mWhite')  # White

# Background colors
print('\033[40mBlack background')  # Black background
print('\033[41mRed background')  # Red background
print('\033[42mGreen background')  # Green background
print('\033[43mYellow background')  # Yellow background
print('\033[44mBlue background')  # Blue background
print('\033[45mMagenta background')  # Magenta background
print('\033[46mCyan background')  # Cyan background
print('\033[47mWhite background')  # White background

# Combining styles
print('\033[1;31mBold Red')  # Bold Red text

# Reset
print('\033[0m')  # Resets all attributes