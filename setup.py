"""This is a distutils setup-script for the Shiboken project

To build the Shiboken, simply execute:
  python setup.py build --qmake=</path/to/qt/bin/qmake> [--cmake=</path/to/cmake>]
or
  python setup.py install --qmake=</path/to/qt/bin/qmake> [--cmake=</path/to/cmake>]
to build and install into your current Python installation.

On Linux you can use option --standalone, to embed Qt libraries to Shiboken distribution

REQUIREMENTS:
- Python: 2.6, 2.7, 3.2, 3.3 and 3.4 is supported
- Cmake: Specify the path to cmake with --cmake option or add cmake to the system path.
- Qt: 4.6, 4.7 and 4.8 is supported. Specify the path to qmake with --qmake option or add qmake to the system path.
"""

__version__ = "1.2.2"

submodules = {
    '1.2.2': [
        ["shiboken", "1.2.2"],
    ],
    '1.2.1': [
        ["shiboken", "1.2.1"],
    ],
    '1.2.0': [
        ["shiboken", "1.2.0"],
    ],
    '1.1.2': [
        ["shiboken", "1.1.2"],
    ],
    '1.1.1': [
        ["shiboken", "1.1.1"],
    ],
}

try:
    import setuptools
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()

import os
import sys
import platform

from distutils import log
from distutils.errors import DistutilsOptionError
from distutils.errors import DistutilsSetupError
from distutils.sysconfig import get_config_var
from distutils.sysconfig import get_python_lib
from distutils.spawn import find_executable
from distutils.command.build import build as _build
from distutils.command.build_ext import build_ext as _build_ext

from setuptools import setup, Extension
from setuptools.command.install import install as _install
from setuptools.command.bdist_egg import bdist_egg as _bdist_egg
from setuptools.command.develop import develop as _develop

from qtinfo import QtInfo
from utils import rmtree
from utils import makefile
from utils import copyfile
from utils import copydir
from utils import run_process
from utils import has_option
from utils import option_value
from utils import update_env_path
from utils import init_msvc_env
from utils import regenerate_qt_resources

# Declare options
OPTION_DEBUG = has_option("debug")
OPTION_RELWITHDEBINFO = has_option('relwithdebinfo')
OPTION_QMAKE = option_value("qmake")
OPTION_CMAKE = option_value("cmake")
OPTION_ONLYPACKAGE = has_option("only-package")
OPTION_STANDALONE = has_option("standalone")
OPTION_VERSION = option_value("version")
OPTION_LISTVERSIONS = has_option("list-versions")
OPTION_MAKESPEC = option_value("make-spec")
OPTION_IGNOREGIT = has_option("ignore-git")
OPTION_JOBS = option_value('jobs')                # number of parallel build jobs
OPTION_JOM = has_option('jom')                    # use jom instead of nmake with msvc
OPTION_BUILDTESTS = has_option("build-tests")
OPTION_OSXARCH = option_value("osx-arch")

if OPTION_QMAKE is None:
    OPTION_QMAKE = find_executable("qmake")
if OPTION_CMAKE is None:
    OPTION_CMAKE = find_executable("cmake")

if sys.platform == "win32":
    if OPTION_MAKESPEC is None:
        OPTION_MAKESPEC = "msvc"
    if not OPTION_MAKESPEC in ["msvc", "mingw"]:
        print("Invalid option --make-spec. Available values are %s" % (["msvc", "mingw"]))
        sys.exit(1)
else:
    if OPTION_MAKESPEC is None:
        OPTION_MAKESPEC = "make"
    if not OPTION_MAKESPEC in ["make"]:
        print("Invalid option --make-spec. Available values are %s" % (["make"]))
        sys.exit(1)

if OPTION_JOM:
    if OPTION_MAKESPEC != "msvc":
        print("Option --jom can only be used with msvc")
        sys.exit(1)

if OPTION_JOBS:
    if sys.platform == 'win32' and not OPTION_JOM:
        print("Option --jobs can only be used with --jom on Windows.")
        sys.exit(1)
    else:
        if not OPTION_JOBS.startswith('-j'):
            OPTION_JOBS = '-j' + OPTION_JOBS
else:
    OPTION_JOBS = ''

if sys.platform == 'darwin' and OPTION_STANDALONE:
    print("--standalone option does not yet work on OSX")


# Show available versions
if OPTION_LISTVERSIONS:
    for v in submodules:
        print("%s" % (v))
        for m in submodules[v]:
            print("  %s %s" % (m[0], m[1]))
    sys.exit(1)

# Change the cwd to our source dir
try:
    this_file = __file__
except NameError:
    this_file = sys.argv[0]
this_file = os.path.abspath(this_file)
if os.path.dirname(this_file):
    os.chdir(os.path.dirname(this_file))
script_dir = os.getcwd()

# Change package version
if OPTION_VERSION:
    if OPTION_IGNOREGIT:
        print("Option --version can not be used together with option --ignore-git")
        sys.exit(1)
    if not os.path.isdir(".git"):
        print("Option --version is available only when shiboken-setup was cloned from git repository")
        sys.exit(1)
    if not OPTION_VERSION in submodules:
        print("""Invalid version specified %s
Use --list-versions option to get list of available versions""" % OPTION_VERSION)
        sys.exit(1)
    __version__ = OPTION_VERSION

    
# Initialize, pull and checkout submodules
if os.path.isdir(".git") and not OPTION_IGNOREGIT and not OPTION_ONLYPACKAGE:
    print("Initializing submodules for Shiboken version %s" % __version__)
    git_update_cmd = ["git", "submodule", "update", "--init"]
    if run_process(git_update_cmd) != 0:
        raise DistutilsSetupError("Failed to initialize the git submodules")
    git_pull_cmd = ["git", "submodule", "foreach", "git", "fetch", "origin"]
    if run_process(git_pull_cmd) != 0:
        raise DistutilsSetupError("Failed to initialize the git submodules")
    git_pull_cmd = ["git", "submodule", "foreach", "git", "pull", "origin", "master"]
    if run_process(git_pull_cmd) != 0:
        raise DistutilsSetupError("Failed to initialize the git submodules")
    submodules_dir = os.path.join(script_dir, "sources")
    for m in submodules[__version__]:
        module_name = m[0]
        module_version = m[1]
        print("Checking out submodule %s to branch %s" % (module_name, module_version))
        module_dir = os.path.join(submodules_dir, module_name)
        os.chdir(module_dir)
        git_checkout_cmd = ["git", "checkout", module_version]
        if run_process(git_checkout_cmd) != 0:
            raise DistutilsSetupError("Failed to initialize the git submodule %s" % module_name)
        os.chdir(script_dir)

# Clean up temp and package folders
for n in ["shiboken_package", "build", "Shiboken-%s" % __version__]:
    d = os.path.join(script_dir, n)
    if os.path.isdir(d):
        print("Removing %s" % d)
        rmtree(d)

# Prepare package folders
for pkg in ["shiboken_package/Shiboken"]:
    pkg_dir = os.path.join(script_dir, pkg)
    os.makedirs(pkg_dir)

class shiboken_install(_install):
    def run(self):
        _install.run(self)
        # Custom script we run at the end of installing - this is the same script
        # run by bdist_wininst
        # If self.root has a value, it means we are being "installed" into
        # some other directory than Python itself (eg, into a temp directory
        # for bdist_wininst to use) - in which case we must *not* run our
        # installer
        if not self.dry_run and not self.root:
            if sys.platform == "win32":
                filename = os.path.join(self.prefix, "Scripts", "shiboken_postinstall.py")
            else:
                filename = os.path.join(self.prefix, "bin", "shiboken_postinstall.py")
            if not os.path.isfile(filename):
                raise RuntimeError("Can't find '%s'" % (filename,))
            print("Executing post install script '%s'..." % filename)
            cmd = [
                os.path.abspath(sys.executable),
                filename,
                "-install"
            ]
            run_process(cmd)

class shiboken_develop(_develop):

    def __init__(self, *args, **kwargs):
        _develop.__init__(self, *args, **kwargs)

    def run(self):
        self.run_command("build")
        _develop.run(self)

class shiboken_bdist_egg(_bdist_egg):

    def __init__(self, *args, **kwargs):
        _bdist_egg.__init__(self, *args, **kwargs)

    def run(self):
        self.run_command("build")
        _bdist_egg.run(self)

class shiboken_build_ext(_build_ext):

    def __init__(self, *args, **kwargs):
        _build_ext.__init__(self, *args, **kwargs)

    def run(self):
        pass

class shiboken_build(_build):

    def __init__(self, *args, **kwargs):
        _build.__init__(self, *args, **kwargs)

    def initialize_options(self):
        _build.initialize_options(self)
        self.make_path = None
        self.make_generator = None
        self.debug = False
        self.script_dir = None
        self.sources_dir = None
        self.build_dir = None
        self.install_dir = None
        self.qmake_path = None
        self.py_executable = None
        self.py_include_dir = None
        self.py_library = None
        self.py_version = None
        self.build_type = "Release"
        self.qtinfo = None
        self.build_tests = False
    
    def run(self):
        platform_arch = platform.architecture()[0]
        log.info("Python architecture is %s" % platform_arch)

        build_type = OPTION_DEBUG and "Debug" or "Release"
        if OPTION_RELWITHDEBINFO:
            build_type = 'RelWithDebInfo'

        # Check env
        make_path = None
        make_generator = None
        if not OPTION_ONLYPACKAGE:
            if OPTION_MAKESPEC == "make":
                make_name = "make"
                make_generator = "Unix Makefiles"
            elif OPTION_MAKESPEC == "msvc":
                nmake_path = find_executable("nmake")
                if nmake_path is None or not os.path.exists(nmake_path):
                    log.info("nmake not found. Trying to initialize the MSVC env...")
                    init_msvc_env(platform_arch, build_type)
                else:
                    log.info("nmake was found in %s" % nmake_path)
                if OPTION_JOM:
                    make_name = "jom"
                    make_generator = "NMake Makefiles JOM"
                else:
                    make_name = "nmake"
                    make_generator = "NMake Makefiles"
            elif OPTION_MAKESPEC == "mingw":
                make_name = "mingw32-make"
                make_generator = "MinGW Makefiles"
            else:
                raise DistutilsSetupError(
                    "Invalid option --make-spec.")
            make_path = find_executable(make_name)
            if make_path is None or not os.path.exists(make_path):
                raise DistutilsSetupError(
                    "You need the program \"%s\" on your system path to compile Shiboken." \
                    % make_name)

            if OPTION_CMAKE is None or not os.path.exists(OPTION_CMAKE):
                raise DistutilsSetupError(
                    "Failed to find cmake."
                    " Please specify the path to cmake with --cmake parameter.")

        if OPTION_QMAKE is None or not os.path.exists(OPTION_QMAKE):
            raise DistutilsSetupError(
                "Failed to find qmake."
                " Please specify the path to qmake with --qmake parameter.")
        
        # Prepare parameters
        py_executable = sys.executable
        py_version = "%s.%s" % (sys.version_info[0], sys.version_info[1])
        py_include_dir = get_config_var("INCLUDEPY")
        py_libdir = get_config_var("LIBDIR")
        py_prefix = get_config_var("prefix")
        if not py_prefix or not os.path.exists(py_prefix):
            py_prefix = sys.prefix
        if sys.platform == "win32":
            py_scripts_dir = os.path.join(py_prefix, "Scripts")
        else:
            py_scripts_dir = os.path.join(py_prefix, "bin")
        if py_libdir is None or not os.path.exists(py_libdir):
            if sys.platform == "win32":
                py_libdir = os.path.join(py_prefix, "libs")
            else:
                py_libdir = os.path.join(py_prefix, "lib")
        if py_include_dir is None or not os.path.exists(py_include_dir):
            if sys.platform == "win32":
                py_include_dir = os.path.join(py_prefix, "include")
            else:
                py_include_dir = os.path.join(py_prefix, "include/python%s" % py_version)
        dbgPostfix = ""
        if build_type == "Debug":
            dbgPostfix = "_d"
        if sys.platform == "win32":
            if OPTION_MAKESPEC == "mingw":
                py_library = os.path.join(py_libdir, "libpython%s%s.a" % \
                    (py_version.replace(".", ""), dbgPostfix))
            else:
                py_library = os.path.join(py_libdir, "python%s%s.lib" % \
                    (py_version.replace(".", ""), dbgPostfix))
        else:
            lib_exts = ['.so']
            if sys.platform == 'darwin':
                lib_exts.append('.dylib')
            if sys.version_info[0] > 2:
                lib_suff = getattr(sys, 'abiflags', None)
            else: # Python 2
                lib_suff = ''
            lib_exts.append('.so.1')
            lib_exts.append('.a') # static library as last gasp

            if sys.version_info[0] == 2 and dbgPostfix:
                # For Python2 add a duplicate set of extensions combined with
                # the dbgPostfix, so we test for both the debug version of
                # the lib and the normal one. This allows a debug Shiboken to
                # be built with a non-debug Python.
                lib_exts = [dbgPostfix + e for e in lib_exts] + lib_exts
                
            libs_tried = []
            for lib_ext in lib_exts:
                lib_name = "libpython%s%s%s" % (py_version, lib_suff, lib_ext)
                py_library = os.path.join(py_libdir, lib_name)
                if os.path.exists(py_library):
                    break
                libs_tried.append(py_library)
            else:
                py_multiarch = get_config_var("MULTIARCH")
                if py_multiarch:
                    try_py_libdir = os.path.join(py_libdir, py_multiarch)
                    libs_tried = []
                    for lib_ext in lib_exts:
                        lib_name = "libpython%s%s%s" % (py_version, lib_suff, lib_ext)
                        py_library = os.path.join(try_py_libdir, lib_name)
                        if os.path.exists(py_library):
                            py_libdir = try_py_libdir
                            break
                        libs_tried.append(py_library)
                    else:
                        raise DistutilsSetupError(
                            "Failed to locate the Python library with %s" %
                            ', '.join(libs_tried))
                else:
                    raise DistutilsSetupError(
                        "Failed to locate the Python library with %s" %
                        ', '.join(libs_tried))
            if py_library.endswith('.a'):
                # Python was compiled as a static library
                log.error("Failed to locate a dynamic Python library, using %s"
                          % py_library)

        qtinfo = QtInfo(OPTION_QMAKE)
        qt_dir = os.path.dirname(OPTION_QMAKE)
        qt_version = qtinfo.version
        if not qt_version:
            log.error("Failed to query the Qt version with qmake %s" % qtinfo.qmake_path)
            sys.exit(1)
        
        # Update the PATH environment variable
        update_env_path([py_scripts_dir, qt_dir])
        
        build_name = "py%s-qt%s-%s-%s" % \
            (py_version, qt_version, platform.architecture()[0], build_type.lower())
        
        script_dir = os.getcwd()
        sources_dir = os.path.join(script_dir, "sources")
        build_dir = os.path.join(script_dir, "shiboken_build", "%s" % build_name)
        install_dir = os.path.join(script_dir, "shiboken_install", "%s" % build_name)
        
        # Try to ensure that tools built by this script (such as shiboken)
        # are found before any that may already be installed on the system.
        update_env_path([os.path.join(install_dir, 'bin')])
        
        # Tell cmake to look here for *.cmake files 
        os.environ['CMAKE_PREFIX_PATH'] = install_dir
        
        self.make_path = make_path
        self.make_generator = make_generator
        self.debug = OPTION_DEBUG
        self.script_dir = script_dir
        self.sources_dir = sources_dir
        self.build_dir = build_dir
        self.install_dir = install_dir
        self.qmake_path = OPTION_QMAKE
        self.py_executable = py_executable
        self.py_include_dir = py_include_dir
        self.py_library = py_library
        self.py_version = py_version
        self.build_type = build_type
        self.qtinfo = qtinfo
        self.site_packages_dir = get_python_lib(1, 0, prefix=install_dir)
        self.build_tests = OPTION_BUILDTESTS
        
        log.info("=" * 30)
        log.info("Package version: %s" % __version__)
        log.info("Build type: %s" % self.build_type)
        log.info("Build tests: %s" % self.build_tests)
        log.info("-" * 3)
        log.info("Make path: %s" % self.make_path)
        log.info("Make generator: %s" % self.make_generator)
        log.info("Make jobs: %s" % OPTION_JOBS)
        log.info("-" * 3)
        log.info("Script directory: %s" % self.script_dir)
        log.info("Sources directory: %s" % self.sources_dir)
        log.info("Build directory: %s" % self.build_dir)
        log.info("Install directory: %s" % self.install_dir)
        log.info("Python site-packages install directory: %s" % self.site_packages_dir)
        log.info("-" * 3)
        log.info("Python executable: %s" % self.py_executable)
        log.info("Python includes: %s" % self.py_include_dir)
        log.info("Python library: %s" % self.py_library)
        log.info("Python prefix: %s" % py_prefix)
        log.info("Python scripts: %s" % py_scripts_dir)
        log.info("-" * 3)
        log.info("Qt qmake: %s" % self.qmake_path)
        log.info("Qt version: %s" % qtinfo.version)
        log.info("Qt bins: %s" % qtinfo.bins_dir)
        log.info("Qt plugins: %s" % qtinfo.plugins_dir)
        log.info("=" * 30)
        
        # Prepare folders
        if not os.path.exists(self.sources_dir):
            log.info("Creating sources folder %s..." % self.sources_dir)
            os.makedirs(self.sources_dir)
        if not os.path.exists(self.build_dir):
            log.info("Creating build folder %s..." % self.build_dir)
            os.makedirs(self.build_dir)
        if not os.path.exists(self.install_dir):
            log.info("Creating install folder %s..." % self.install_dir)
            os.makedirs(self.install_dir)
        
        if not OPTION_ONLYPACKAGE:
            # Build extensions
            for ext in ['shiboken']:
                self.build_extension(ext)

        # Build patchelf if needed
        self.build_patchelf()

        # Prepare packages
        self.prepare_packages()
        
        # Build packages
        _build.run(self)

    def build_patchelf(self):
        if not sys.platform.startswith('linux'):
            return
        log.info("Building patchelf...")
        module_src_dir = os.path.join(self.sources_dir, "patchelf")
        build_cmd = [
            "g++",
            "%s/patchelf.cc" % (module_src_dir),
            "-o",
            "patchelf",
        ]
        if run_process(build_cmd) != 0:
            raise DistutilsSetupError("Error building patchelf")

    def build_extension(self, extension):
        log.info("Building module %s..." % extension)
        
        # Prepare folders
        os.chdir(self.build_dir)
        module_build_dir = os.path.join(self.build_dir,  extension)
        if os.path.exists(module_build_dir):
            log.info("Deleting module build folder %s..." % module_build_dir)
            rmtree(module_build_dir)
        log.info("Creating module build folder %s..." % module_build_dir)
        os.makedirs(module_build_dir)
        os.chdir(module_build_dir)
        
        module_src_dir = os.path.join(self.sources_dir, extension)
        
        # Build module
        cmake_cmd = [
            OPTION_CMAKE,
            "-G", self.make_generator,
            "-DQT_QMAKE_EXECUTABLE=%s" % self.qmake_path,
            "-DBUILD_TESTS=%s" % self.build_tests,
            "-DDISABLE_DOCSTRINGS=True",
            "-DCMAKE_BUILD_TYPE=%s" % self.build_type,
            "-DCMAKE_INSTALL_PREFIX=%s" % self.install_dir,
            module_src_dir
        ]
        if sys.version_info[0] > 2:
            cmake_cmd.append("-DPYTHON3_EXECUTABLE=%s" % self.py_executable)
            cmake_cmd.append("-DPYTHON3_INCLUDE_DIR=%s" % self.py_include_dir)
            cmake_cmd.append("-DPYTHON3_LIBRARY=%s" % self.py_library)
            if self.build_type.lower() == 'debug':
                cmake_cmd.append("-DPYTHON3_DBG_EXECUTABLE=%s" % self.py_executable)
                cmake_cmd.append("-DPYTHON3_DEBUG_LIBRARY=%s" % self.py_library)
        else:
            cmake_cmd.append("-DPYTHON_EXECUTABLE=%s" % self.py_executable)
            cmake_cmd.append("-DPYTHON_INCLUDE_DIR=%s" % self.py_include_dir)
            cmake_cmd.append("-DPYTHON_LIBRARY=%s" % self.py_library)
            if self.build_type.lower() == 'debug':
                cmake_cmd.append("-DPYTHON_DEBUG_LIBRARY=%s" % self.py_library)

        if sys.platform == 'win32':
            cmake_cmd.append("-DCMAKE_DEBUG_POSTFIX=_d")

        cmake_cmd.append("-DCMAKE_INSTALL_RPATH_USE_LINK_PATH=yes")
        if sys.version_info[0] > 2:
            cmake_cmd.append("-DUSE_PYTHON3=ON")
        
        if sys.platform == 'darwin':
            cmake_cmd.append('-DALTERNATIVE_QT_INCLUDE_DIR=' + self.qtinfo.headers_dir)
            
            if OPTION_OSXARCH:
                # also tell cmake which architecture to use 
                cmake_cmd.append("-DCMAKE_OSX_ARCHITECTURES:STRING={}".format(OPTION_OSXARCH))

        log.info("Configuring module %s (%s)..." % (extension,  module_src_dir))
        if run_process(cmake_cmd) != 0:
            raise DistutilsSetupError("Error configuring " + extension)
        
        log.info("Compiling module %s..." % extension)
        cmd_make = [self.make_path]
        if OPTION_JOBS:
            cmd_make.append(OPTION_JOBS)
        if run_process(cmd_make) != 0:
            raise DistutilsSetupError("Error compiling " + extension)
        
        log.info("Generating Shiboken documentation %s..." % extension)
        if run_process([self.make_path, "doc"]) != 0:
            raise DistutilsSetupError("Error generating documentation " + extension)
        
        log.info("Installing module %s..." % extension)
        if run_process([self.make_path, "install/fast"]) != 0:
            raise DistutilsSetupError("Error pseudo installing " + extension)
        
        os.chdir(self.script_dir)

    def prepare_packages(self):
        log.info("Preparing packages...")
        version_str = "%sqt%s%s" % (__version__, self.qtinfo.version.replace(".", "")[0:3],
            self.debug and "dbg" or "")
        vars = {
            "site_packages_dir": self.site_packages_dir,
            "sources_dir": self.sources_dir,
            "install_dir": self.install_dir,
            "build_dir": self.build_dir,
            "script_dir": self.script_dir,
            "dist_dir": os.path.join(self.script_dir, 'shiboken_package'),
            "py_version": self.py_version,
            "qt_version": self.qtinfo.version,
            "qt_bin_dir": self.qtinfo.bins_dir,
            "qt_lib_dir": self.qtinfo.libs_dir,
            "qt_plugins_dir": self.qtinfo.plugins_dir,
            "qt_imports_dir": self.qtinfo.imports_dir,
            "qt_translations_dir": self.qtinfo.translations_dir,
            "version": version_str,
        }
        os.chdir(self.script_dir)
        if sys.platform == "win32":
            vars['dbgPostfix'] = OPTION_DEBUG and "_d" or ""
            return self.prepare_packages_win32(vars)
        return self.prepare_packages_posix(vars)

    def prepare_packages_posix(self, vars):
        if sys.platform.startswith('linux'):
            # patchelf -> Shiboken/patchelf
            copyfile(
                "{script_dir}/patchelf",
                "{dist_dir}/Shiboken/patchelf",
                vars=vars)
            so_ext = '.so'
            so_star = so_ext + '.*'
        elif sys.platform == 'darwin':
            so_ext = '.dylib'
            so_star = so_ext
        # <build>/shiboken/doc/html/* -> <setup>/Shiboken/docs/shiboken
        copydir(
            "{build_dir}/shiboken/doc/html",
            "{dist_dir}/Shiboken/docs/shiboken",
            force=False, vars=vars)
        # <install>/lib/site-packages/shiboken.so -> <setup>/Shiboken/shiboken.so
        copyfile(
            "{site_packages_dir}/shiboken.so",
            "{dist_dir}/Shiboken/shiboken.so",
            vars=vars)
        # <install>/bin/* -> Shiboken/
        copydir(
            "{install_dir}/bin/",
            "{dist_dir}/Shiboken",
            filter=[
                "shiboken",
            ],
            recursive=False, vars=vars)
        # <install>/lib/lib* -> Shiboken/
        copydir(
            "{install_dir}/lib/",
            "{dist_dir}/Shiboken",
            filter=[
                "libshiboken*" + so_star,
            ],
            recursive=False, vars=vars)
        # <install>/include/* -> <setup>/Shiboken/include
        copydir(
            "{install_dir}/include",
            "{dist_dir}/Shiboken/include",
            vars=vars)
        # Copy Qt libs to package
        if OPTION_STANDALONE:
            if sys.platform == 'darwin':
                raise RuntimeError('--standalone not yet supported for OSX')
            # <qt>/lib/* -> <setup>/Shiboken
            copydir("{qt_lib_dir}", "{dist_dir}/Shiboken",
                filter=[
                    "libQtCore*.so.?", "libQtXml*.so.?",
                ],
                recursive=False, vars=vars)

    def prepare_packages_win32(self, vars):
        pdbs = ['*.pdb'] if self.debug or self.build_type == 'RelWithDebInfo' else []       
        # <build>/shiboken/doc/html/* -> <setup>/Shiboken/docs/shiboken
        copydir(
            "{build_dir}/shiboken/doc/html",
            "{dist_dir}/Shiboken/docs/shiboken",
            force=False, vars=vars)
        # <install>/lib/site-packages/shiboken.pyd -> <setup>/Shiboken/shiboken.pyd
        copyfile(
            "{site_packages_dir}/shiboken{dbgPostfix}.pyd",
            "{dist_dir}/Shiboken/shiboken{dbgPostfix}.pyd",
            vars=vars)
        if self.debug or self.build_type == 'RelWithDebInfo':
            copyfile(
                "{build_dir}/shiboken/shibokenmodule/shiboken{dbgPostfix}.pdb",
                "{dist_dir}/Shiboken/shiboken{dbgPostfix}.pdb",
                vars=vars)        
        # <install>/bin/*.exe,*.dll,*.pdb -> Shiboken/
        copydir(
            "{install_dir}/bin/",
            "{dist_dir}/Shiboken",
            filter=["*.exe", "*.dll"] + pdbs,
            recursive=False, vars=vars)
        # <install>/lib/*.lib -> Shiboken/
        copydir(
            "{install_dir}/lib/",
            "{dist_dir}/Shiboken",
            filter=["*.lib"],
            recursive=False, vars=vars)
        # <install>/include/* -> <setup>/Shiboken/include
        copydir(
            "{install_dir}/include",
            "{dist_dir}/Shiboken/include",
            vars=vars)
        
        # <qt>/bin/*.dll -> <setup>/Shiboken
        copydir("{qt_bin_dir}", "{dist_dir}/Shiboken",
            filter=[
                "QtCore4.dll",
                "QtXml4.dll"],
            recursive=False, vars=vars)
        if self.debug:
            # <qt>/bin/*d4.dll -> <setup>/Shiboken
            copydir("{qt_bin_dir}", "{dist_dir}/Shiboken",
                filter=["QtCored4.dll", "QtXmld4.dll"] + pdbs,
                recursive=False, vars=vars)

        if self.debug  or self.build_type == 'RelWithDebInfo':
            # <qt>/lib/*.pdb -> <setup>/Shiboken
            copydir("{qt_lib_dir}", "{dist_dir}/Shiboken",
                filter=["QtCore*.pdb", "QtXml*.pdb"],
                recursive=False, vars=vars)

        # pdb files for libshiboken
        if self.debug or self.build_type == 'RelWithDebInfo':
            copyfile(
                "{build_dir}/shiboken/libshiboken/shiboken-python{py_version}{dbgPostfix}.pdb",
                "{dist_dir}/Shiboken/shiboken-python{py_version}{dbgPostfix}.pdb",
                vars=vars)


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "Shiboken",
    version = __version__,
    description = ("Shiboken generates bindings for C++ libraries using CPython source code"),
    long_description = open("README.rst").read() + "\n" +
                       open("CHANGES.rst").read(),
    options = {
        "bdist_wininst": {
            "install_script": "shiboken_postinstall.py",
        },
        "bdist_msi": {
            "install_script": "shiboken_postinstall.py",
        },
    },
    scripts = [
        "shiboken_postinstall.py"
    ],
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Environment :: MacOS X',
        'Environment :: X11 Applications :: Qt',
        'Environment :: Win32 (MS Windows)',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX',
        'Operating System :: POSIX :: Linux',
        'Operating System :: Microsoft',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: C++',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Database',
        'Topic :: Software Development',
        'Topic :: Software Development :: Code Generators',
    ],
    keywords = 'Qt',
    author = 'PySide Team',
    author_email = 'contact@pyside.org',
    url = 'http://www.pyside.org',
    license = 'LGPL',
    packages = ['Shiboken'],
    package_dir = {'': 'shiboken_package'},
    include_package_data = True,
    zip_safe = False,
    cmdclass = {
        'build': shiboken_build,
        'build_ext': shiboken_build_ext,
        'bdist_egg': shiboken_bdist_egg,
        'develop': shiboken_develop,
        'install': shiboken_install,
    },
    
    # Add a bogus extension module (will never be built here since we are
    # overriding the build command to do it using cmake) so things like
    # bdist_egg will know that there are extension modules and will name the
    # dist with the full platform info.
    ext_modules = [Extension('QtCore', [])],
    ext_package = 'Shiboken',
)
