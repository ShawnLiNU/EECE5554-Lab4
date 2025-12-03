# Lab 4 Autograder



### 1. Install Docker
```bash
sudo apt-get update
sudo apt-get install -y docker.io
```

### 2. Setup Autograder
```bash
cd lab4-autograder
chmod +x grade.sh
```
### 3. Usage
Run Autograder
```
./grade.sh /path/to/workspace
```
There will be prompt for asking password for sudo permission.

The expeted workspace structure is:
```
EECE5554/
└── lab4-imu/
   └── vn_driver/                    # Package name must be vn_driver
       ├── vn_driver/                # Python package directory
       │   └── driver.py             # Driver implementation
       ├── msg/                      # Message directory (can be any name)
       │   └── *.msg                 # Message file (any name ending in .msg)
       ├── launch/                   # Launch directory
       │   └── launch.py             # Launch file (any name with 'launch')
       ├── CMakeLists.txt
       └── package.xml

```


NOTE: by running this code, the autograder will delete your buil, install and log folder under your workspace.

If you want to delete the folder that autograder created, please use
```
sudo rm -rf <replace this with folder name>
```