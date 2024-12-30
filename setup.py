from setuptools import setup, find_packages

# Read requirements.txt
with open("requirements.txt") as f:
    install_require = f.read().splitlines()

setup(
    name="IDesign_Cybever",
    version="0.1.0",
    license='MIT',
    description='Agent based indoor layout by following IDesign',
    author='Chen Lin, ...',
    author_email='chen@cybever.ai',
    packages=find_packages(),
    install_requires=install_require,  # Use the dependencies from requirements.txt
)
