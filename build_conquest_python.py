#!/usr/bin/env python3

import sys
import subprocess
import os
import stat
import shutil
import tempfile
import multiprocessing

from pathlib import Path

from distutils.version import StrictVersion

toolbase = Path('/opt/ccdc/third-party')
toolbase.mkdir(parents=True, exist_ok=True)
source_downloads_base = Path('/opt/ccdc/third-party-sources/downloads')
source_downloads_base.mkdir(parents=True, exist_ok=True)
source_extracted_base = Path('/opt/ccdc/third-party-sources/extracted')
source_extracted_base.mkdir(parents=True, exist_ok=True)
source_builds_base = Path('/opt/ccdc/third-party-sources/builds')
source_builds_base.mkdir(parents=True, exist_ok=True)
build_logs = Path('/opt/ccdc/third-party-sources/logs')
build_logs.mkdir(parents=True, exist_ok=True)

mac = sys.platform == 'darwin'
if mac:
    SDKROOT = subprocess.check_output(
        ['xcrun', '--show-sdk-path'])[:-1].decode('utf8')
    # For an explanation of these settings see:
    # https://developer.apple.com/library/ios/documentation/DeveloperTools/Conceptual/cross_development/Configuring/configuring.html
    assert os.path.exists(SDKROOT)
    MACOSX_DEPLOYMENT_TARGET = '10.12'


class Package(object):
    '''Base for anything installable'''
    name = None
    version = None

    @property
    def install_directory(self):
        '''Return the canonical installation directory'''
        return toolbase / self.name / f'{self.name}-{self.version}'

    @property
    def include_directories(self):
        '''Return the directories clients must add to their include path'''
        return [self.install_directory / 'include']

    @property
    def library_link_directories(self):
        '''Return the directories clients must add to their library link path'''
        return [self.install_directory / 'lib']

    @property
    def source_archives(self):
        '''Map of archive file/url to fetch'''
        return {}

    def fetch_source_archives(self):
        import urllib.request
        for filename, url in self.source_archives.items():
            if (source_downloads_base / filename).exists():
                print(
                    f'Skipping download of existing {source_downloads_base / filename}')
                continue
            print(f'Fetching {url} to {source_downloads_base / filename}')
            with urllib.request.urlopen(url) as response:
                with open(source_downloads_base / filename, 'wb') as final_file:
                    shutil.copyfileobj(response, final_file)

    def extract_source_archives(self):
        for source_archive_filename in self.source_archives.keys():
            self.extract_archive(source_downloads_base /
                                 source_archive_filename, self.source_extracted)

    def extract_archive(self, path, where):
        '''untar a file with any reasonable suffix'''
        print(f'Extracting {path} to {where}')
        if '.zip' in path.suffixes:
            self.system(['unzip', '-q', '-o', str(path)], cwd=where)
            return
        if '.bz2' in path.suffixes:
            flags = 'jxf'
        elif '.gz' in path.suffixes:
            flags = 'zxf'
        elif '.tgz' in path.suffixes:
            flags = 'zxf'
        elif '.xz' in path.suffixes:
            flags = 'xf'
        else:
            raise AttributeError(f"Can't extract {path}")

        self.system(['tar', flags, str(path)], cwd=where)

    def patch_sources(self):
        '''Override to patch source code after extraction'''
        pass

    @property
    def source_downloads(self):
        p = source_downloads_base / self.name
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def source_extracted(self):
        p = source_extracted_base / self.name
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def main_source_directory_path(self):
        return self.source_extracted / f'{self.name}-{self.version}'

    @property
    def build_directory_path(self):
        p = source_builds_base / self.name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def cleanup(self):
        try:
            shutil.rmtree(self.source_extracted, ignore_errors=True)
            print(f'Cleaned up {self.source_extracted}')
        except OSError:
            pass
        try:
            shutil.rmtree(self.build_directory_path, ignore_errors=True)
            print(f'Cleaned up {self.build_directory_path}')
        except OSError:
            pass

    @property
    def configuration_script(self):
        return None

    @property
    def arguments_to_configuration_script(self):
        return [f'--prefix={self.install_directory}']

    @property
    def cxxflags(self):
        flags = [
            '-O2'
        ]
        if mac:
            flags.extend([
                '-arch', 'x86_64',
                '-isysroot', SDKROOT,
                f'-mmacosx-version-min={MACOSX_DEPLOYMENT_TARGET}',
            ])
        return flags

    @property
    def ldflags(self):
        flags = []
        if mac:
            flags.extend([
                '-arch', 'x86_64',
                '-isysroot', SDKROOT,
                f'-mmacosx-version-min={MACOSX_DEPLOYMENT_TARGET}',
            ])
        return flags

    @property
    def cflags(self):
        flags = [
            '-O2'
        ]
        if mac:
            flags.extend([
                '-arch', 'x86_64',
                '-isysroot', SDKROOT,
                f'-mmacosx-version-min={MACOSX_DEPLOYMENT_TARGET}',
            ])
        return flags

    @property
    def environment_for_configuration_script(self):
        env = dict(os.environ)
        if self.cflags:
            env['CFLAGS'] = ' '.join(self.cflags)
        if self.cxxflags:
            env['CXXFLAGS'] = ' '.join(self.cxxflags)
        if self.ldflags:
            env['LDFLAGS'] = ' '.join(self.ldflags)
        return env

    def run_configuration_script(self):
        '''run the required commands to configure a package'''
        if not self.configuration_script:
            print(f'Skipping configuration script for {self.name}')
            return
        st = os.stat(self.configuration_script)
        os.chmod(self.configuration_script, st.st_mode | stat.S_IEXEC)
        self.system(
            [str(self.configuration_script)] +
            self.arguments_to_configuration_script,
            env=self.environment_for_configuration_script, cwd=self.build_directory_path)

    @property
    def environment_for_build_command(self):
        return self.environment_for_configuration_script

    def run_build_command(self):
        '''run the required commands to build a package after configuration'''
        pass

    def run_install_command(self):
        '''run the required commands to install a package'''
        pass

    def logfile_path(self, task):
        '''Canonical log file for a particular task'''
        return build_logs / f'{self.name}-{self.version}-{task}.log'

    def system(self, command, cwd=None, env=None, append_log=False):
        '''execute command, logging in the appropriate logfile'''
        task = sys._getframe(1).f_code.co_name
        print(f'{self.name} {task}')
        if isinstance(command, str):
            command = [command]
        print(f'Running {command}')
        openmode = 'a' if append_log else 'w'
        with open(self.logfile_path(task), openmode) as f:
            output = ''
            p = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd, env=env)
            while True:
                retcode = p.poll()
                l = p.stdout.readline().decode('utf-8')
                print(l.rstrip())
                output += l
                f.write(l)
                if retcode is not None:
                    break
            assert p.returncode is not None
            if p.returncode != 0:
                print(f'Failed process environment was {env}')
                raise subprocess.CalledProcessError(
                    returncode=p.returncode, cmd=command, output=output)

    def verify(self):
        '''Override this function to verify that the install has
        produced something functional.'''
        pass

    def build(self):
        self.cleanup()
        self.fetch_source_archives()
        self.extract_source_archives()
        self.patch_sources()
        self.run_configuration_script()
        self.run_build_command()
        self.run_install_command()
        self.verify()

    def update_dylib_id(self, library_path, new_id):
        '''MacOS helper to change a library's identifier'''
        self.system(['install_name_tool', '-id', new_id, str(library_path)])

    def change_dylib_lookup(self, library_path, from_path, to_path):
        '''MacOS helper to change the path where libraries and executables look for other libraries'''
        self.system(['install_name_tool', '-change',
                     from_path, to_path, str(library_path)])

    def patch(self, fname, *subs):
        with open(fname) as read_file:
            txt = read_file.read()
        for (old, new) in subs:
            txt = txt.replace(old, new)
        with open(fname, 'w') as out:
            out.write(txt)

######################################################################
#   Mixins for installation.  Derive from one of these before Package
#   to get the best out of Python's MRO
######################################################################


class GnuMakeMixin(object):
    '''Make based build'''

    def run_build_command(self):
        self.system(['make', f'-j{multiprocessing.cpu_count()}'],
                    env=self.environment_for_build_command, cwd=self.build_directory_path)


class MakeInstallMixin(object):
    '''Make install (rather than the default do nothing install)'''

    def run_install_command(self):
        self.system(['make', 'install'],
                    env=self.environment_for_build_command, cwd=self.build_directory_path)


class AutoconfMixin(GnuMakeMixin, MakeInstallMixin, object):
    '''Autoconf based configure script'''
    @property
    def configuration_script(self):
        return self.main_source_directory_path / 'configure'


class InstallInConquestPythonMixin(object):
    @property
    def install_directory(self):
        '''Tcl and other packages must be installed under the same directory as Python on Linux
           and as a Framework on MacOS to work for the purposes of ConQuest'''
        return ConquestPythonPackage().install_directory


class InstallInConquestPythonBaseMixin(object):
    @property
    def install_directory(self):
        '''The nuance with descendants of this class is that these libraries will be installed under the Python Framework on MacOS'''
        return ConquestPythonPackage().python_base_directory

# Individual packages

class ZlibPackage(InstallInConquestPythonBaseMixin, AutoconfMixin, Package):
    '''Zlib'''
    name = 'zlib'
    version = '1.2.11'

    @property
    def source_archives(self):
        return {
            f'zlib-{self.version}.tar.xz': f'https://www.zlib.net/zlib-{self.version}.tar.xz'
        }

    @property
    def arguments_to_configuration_script(self):
        return super().arguments_to_configuration_script + ['--shared']


class SqlitePackage(InstallInConquestPythonBaseMixin, AutoconfMixin, Package):
    '''SQLite'''
    name = 'sqlite'
    version = '3.31.1'
    tarversion = '3310100'

    @property
    def source_archives(self):
        return {
            f'sqlite-autoconf-{self.tarversion}.tar.gz': f'https://www.sqlite.org/2020/sqlite-autoconf-{self.tarversion}.tar.gz'
        }

    @property
    def main_source_directory_path(self):
        return self.source_extracted / f'{self.name}-autoconf-{self.tarversion}'

    @property
    def cflags(self):
        return super().cflags + [
            '-DSQLITE_ENABLE_FTS3',
            '-DSQLITE_ENABLE_FTS4',
            '-DSQLITE_ENABLE_FTS5',
            '-DSQLITE_ENABLE_EXPLAIN_COMMENTS',
            '-DSQLITE_ENABLE_NULL_TRIM',
            '-DSQLITE_MAX_COLUMN=10000',
        ]

    @property
    def ldflags(self):
        return super().ldflags + [
            '-lm'
        ]


class OpensslPackage(InstallInConquestPythonBaseMixin, AutoconfMixin, Package):
    ''' Most of these settings have been based on the Homebrew Formula that can be found here for reference
    https://github.com/Homebrew/homebrew-core/blob/5ab9766e70776ef1702f8d40c8ef5159252c31be/Formula/openssl%401.1.rb
    '''
    name = 'openssl'
    version = '1.1.1f'

    @property
    def source_archives(self):
        return {
            f'openssl-{self.version}.tar.gz': f'https://www.openssl.org/source/openssl-{self.version}.tar.gz'
        }

    @property
    def configuration_script(self):
        return self.main_source_directory_path / 'Configure'

    @property
    def arguments_to_configuration_script(self):
        args = super().arguments_to_configuration_script + [
            '--release',
            f'--openssldir={self.install_directory}/ssl',
            'no-ssl3',
            'no-ssl3-method',
            'no-zlib',
        ]
        if mac:
            args += ['darwin64-x86_64-cc', 'enable-ec_nistp_64_gcc_128']
        else:
            args += ['linux-x86_64', 'enable-ec_nistp_64_gcc_128']
        return args

    @property
    def environment_for_configuration_script(self):
        env = super().environment_for_configuration_script
        if env.pop("OPENSSL_LOCAL_CONFIG_DIR", None):
            print(
                'Removed OPENSSL_LOCAL_CONFIG_DIR from the environment to avoid interference')
        return env

    def run_configuration_script(self):
        '''OpenSSL has it's own interesting configuration script that runs via Perl'''
        self.system(
            ['perl', str(self.configuration_script)] +
            self.arguments_to_configuration_script,
            env=self.environment_for_configuration_script, cwd=self.build_directory_path)

    def run_install_command(self):
        super().run_install_command()
        if mac:
            libcrypto_libpath = Path('lib/libcrypto.1.1.dylib')
            self.update_dylib_id(self.install_directory /
                                 libcrypto_libpath, 'libcrypto.1.1.dylib')

            libssl_libpath = Path('lib/libssl.1.1.dylib')
            self.update_dylib_id(self.install_directory /
                                 libssl_libpath, 'libssl.1.1.dylib')
            self.change_dylib_lookup(self.install_directory / libssl_libpath, str(
                self.install_directory / libcrypto_libpath), '@rpath/libcrypto.1.1.dylib')
        # python build needs .a files in a directory away from .dylib
        static_libs_path = self.install_directory / 'staticlibs'
        static_libs_path.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.install_directory / 'lib' /
                        'libssl.a', static_libs_path / 'libssl.a')
        shutil.copyfile(self.install_directory / 'lib' /
                        'libcrypto.a', static_libs_path / 'libcrypto.a')

    def verify(self):
        # If this fails, take a look here!!!!
        # Perl is used by the openssl documentation schema (Text::Template)
        # and many Perl packages are used by the httpdtest perl framework.
        # To deploy many of these using RHEL 7 packages, use
        # $ sudo yum install perl-core perl-Module-Load-Conditional \
        #     perl-HTTP-DAV perl-LWP-Protocol-https perl-AnyEvent-HTTP \
        #     perl-Crypt-SSLeay perl-Net-SSLGlue perl-DateTime \
        #     perl-Module-Build-Tiny perl-Test-LeakTrace perl-Test-TCP

        # And use CPAN for the packages not distributed with the OS as listed above
        # (note the RHEL 7 package perl-Text-Template is too old for use by OpenSSL);
        # $ cpan install Text::Template Protocol::HTTP2::Client
        env = self.environment_for_configuration_script
        self.system(
            ['make', 'test'],
            env=env, cwd=self.build_directory_path)


class TclPackage(InstallInConquestPythonMixin, AutoconfMixin, Package):
    name = 'tcl'
    version = '8.6.10'

    @property
    def source_archives(self):
        return {
            f'tcl{self.version}-src.tar.gz': f'https://prdownloads.sourceforge.net/tcl/tcl{self.version}-src.tar.gz'
        }

    def extract_source_archives(self):
        super().extract_source_archives()
        # Remove packages we don't want to build
        shutil.rmtree(self.main_source_directory_path /
                      'pkgs' / 'sqlite3.30.1.2')
        shutil.rmtree(self.main_source_directory_path / 'pkgs' / 'tdbc1.1.1')
        shutil.rmtree(self.main_source_directory_path /
                      'pkgs' / 'tdbcmysql1.1.1')
        shutil.rmtree(self.main_source_directory_path /
                      'pkgs' / 'tdbcodbc1.1.1')
        shutil.rmtree(self.main_source_directory_path /
                      'pkgs' / 'tdbcpostgres1.1.1')
        shutil.rmtree(self.main_source_directory_path /
                      'pkgs' / 'tdbcsqlite3-1.1.1')

    @property
    def main_source_directory_path(self):
        return self.source_extracted / f'{self.name}{self.version}'

    @property
    def environment_for_configuration_script(self):
        env = super().environment_for_configuration_script
        if mac:
            env['ac_cv_path_tclsh'] = ''
        return env

    @property
    def configuration_script(self):
        # Configuration on MacOS is handled by wizardry in the GNUmakefile in tksource/macosx
        # By returning None, we skip the configuration step in the base Package class
        if mac:
            return None
        # Linux installation works by installing in the destination python directory
        return self.main_source_directory_path / 'unix' / 'configure'

    # This is only used on linux actually
    @property
    def arguments_to_configuration_script(self):
        return super().arguments_to_configuration_script + ['--enable-shared']

    def run_build_command(self):
        if mac:
            self.system([
                'make',
                f'-j{multiprocessing.cpu_count()}',
                '-sw',
                'deploy',
                f'INSTALL_ROOT={self.install_directory}',
                f'PREFIX=""',
            ],
                env=self.environment_for_configuration_script, cwd=self.main_source_directory_path / 'macosx')

            # Link tclsh to the actual location of Tcl, rather than where it
            # would have been without the INSTALL_ROOT argument.
            # Without this, installing Tcl will fail while generating documentation.
            tcl_build_dir = self.main_source_directory_path.parent / 'build' / 'tcl'
            incorrect_location = Path(
                '/') / self.tcl_versioned_framework_path_in_library / 'Tcl'
            correct_location = tcl_build_dir / 'Deployment' / \
                self.tcl_versioned_framework_path / 'Tcl'
            self.change_dylib_lookup(
                tcl_build_dir / 'Deployment' / 'tclsh', incorrect_location, correct_location)
        else:
            super().run_build_command()

    @property
    def tcl_versioned_framework_path(self):
        return Path('Tcl.framework') / 'Versions' / '8.6'

    @property
    def tcl_versioned_framework_path_in_library(self):
        return Path('Library') / 'Frameworks' / self.tcl_versioned_framework_path

    @property
    def include_directories(self):
        '''Return the directories clients must add to their include path'''
        if mac:
            return [self.install_directory / 'Library' / 'Frameworks' / 'Tcl.framework' / 'Headers']
        return [self.install_directory / 'include']

    def run_install_command(self):
        if mac:
            self.system([
                'make',
                f'-j{multiprocessing.cpu_count()}',
                '-sw',
                'install-deploy',
                f'INSTALL_ROOT={self.install_directory}',
                f'PREFIX=""',
                f'TCL_LIB_SPEC="{self.install_directory / "Library" / "Frameworks"}"',
            ],
                env=self.environment_for_configuration_script, cwd=self.main_source_directory_path / 'macosx')
            # copy msgcat.tcl because pyinstaller won't pick up modules
            shutil.copytree(
                self.main_source_directory_path / 'library' / 'msgcat',
                self.install_directory /
                'Library' / 'Frameworks' / 'Tcl.framework' / 'Resources' / 'Scripts' / 'msgcat'
            )
        # # Fix where Tcl and Tk think they are located.
        # for tcltk_lib in [tcl_lib, tk_lib]:
        #     # 755
        #     os.chmod(tcltk_lib,
        #         stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH )
        #     change_install_id(tcltk_lib)
        else:
            super().run_install_command()


class TkPackage(InstallInConquestPythonMixin, AutoconfMixin, Package):
    name = 'tk'
    version = '8.6.10'

    @property
    def source_archives(self):
        return {
            f'tk{self.version}-src.tar.gz': f'https://prdownloads.sourceforge.net/tcl/tk{self.version}-src.tar.gz'
        }

    @property
    def main_source_directory_path(self):
        return self.source_extracted / f'{self.name}{self.version}'

    @property
    def environment_for_configuration_script(self):
        env = super().environment_for_configuration_script
        if mac:
            env['ac_cv_path_tclsh'] = ''
        return env

    @property
    def configuration_script(self):
        # Configuration on MacOS is handled by wizardry in the GNUmakefile in tksource/macosx
        # By returning None, we skip the configuration step in the base Package class
        if mac:
            return None
        # Linux installation works by installing in the destination python directory
        return self.main_source_directory_path / 'unix' / 'configure'

    # This is only used on linux actually
    @property
    def arguments_to_configuration_script(self):
        return super().arguments_to_configuration_script + [
            f'--with-tcl={ TclPackage().install_directory / "lib" }'
        ]

    def run_build_command(self):
        if mac:
            pass
        else:
            super().run_build_command()

    def run_install_command(self):
        if mac:
            self.system([
                'make',
                f'-j{multiprocessing.cpu_count()}',
                '-sw',
                'install-deploy',
                f'INSTALL_ROOT={self.install_directory}',
                f'PREFIX=""',
                f'TCLSH_DIR="{self.install_directory / "bin"}"',
                f'TCL_FRAMEWORK_DIR="{self.install_directory / "Library" / "Frameworks"}"',
            ],
                env=self.environment_for_configuration_script, cwd=self.main_source_directory_path / 'macosx')
            # Link tclsh to the actual location of Tcl, rather than where it
            # would have been without the INSTALL_ROOT argument.
            # Without this, installing Tcl will fail while generating documentation.
            # tcl_build_dir = self.main_source_directory_path.parent / 'build' / 'tcl'
            # incorrect_location = Path('/') / self.tcl_versioned_framework_path_in_library / 'Tcl'
            # correct_location = tcl_build_dir / 'Deployment' / self.tcl_versioned_framework_path / 'Tcl'
            # self.change_dylib_lookup(tcl_build_dir / 'Deployment' / 'tclsh', incorrect_location, correct_location)
            # # tcl_framework_suffix = os.path.join('/Library', 'Frameworks', 'Tcl.framework')
            # tcl_lib_suffix = os.path.join(tcl_framework_suffix, 'Versions', tcltk_ver, 'Tcl')
            # tcl_framework = self.directory + tcl_framework_suffix
            # tcl_lib = self.directory + tcl_lib_suffix
            # tk_framework = os.path.join(self.directory, 'Library', 'Frameworks', 'Tk.framework')
            # tk_lib = os.path.join(tk_framework, 'Versions', tcltk_ver, 'Tk')
            # change_dependency_location(tcl_lib_suffix, tcl_lib, tk_lib)
        # # Fix where Tcl and Tk think they are located.
        # for tcltk_lib in [tcl_lib, tk_lib]:
        #     # 755
        #     os.chmod(tcltk_lib,
        #         stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH )
        #     change_install_id(tcltk_lib)

        else:
            super().run_install_command()

    @property
    def include_directories(self):
        '''Return the directories clients must add to their include path'''
        if mac:
            return [self.install_directory / 'Library' / 'Frameworks' / 'Tk.framework' / 'Headers']
        return [self.install_directory / 'include']


class ToglPackage(InstallInConquestPythonMixin, AutoconfMixin, Package):
    name = 'togl'
    version = 'windows-ci'

    @property
    def source_archives(self):
        return {
            f'Togl-{self.version}.zip': f'https://github.com/rockdreamer/togl/archive/{self.version}.zip'
        }

    @property
    def main_source_directory_path(self):
        return self.source_extracted / f'{self.name}-{self.version}'

    @property
    def build_directory_path(self):
        '''The autoconf script is a bit rubbish, only works in-source :('''
        return self.main_source_directory_path

    @property
    def cflags(self):
        if mac:
            return super().cflags + [
                '-I.',
                '-I/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/System/Library/Frameworks/OpenGL.framework/Headers',
            ]
        return super().cflags + ['-I.']

    @property
    def ldflags(self):
        if mac:
            return super().ldflags + ['-framework', 'OpenGL']
        return super().ldflags

    @property
    def environment_for_configuration_script(self):
        env = super().environment_for_configuration_script
        env['PATH'] = env['PATH'] + os.pathsep + \
            str(self.install_directory / 'bin')
        return env

    @property
    def arguments_to_configuration_script(self):
        args = super().arguments_to_configuration_script
        if mac:
            args += [
                f'--with-tcl={ TclPackage().install_directory / "lib" }',
                f'--libdir={ TclPackage().install_directory / "Library" / "Tcl"}',
                f'--with-tcl={ TclPackage().install_directory / "Library" / "Frameworks" / "Tcl.framework"}',
                f'--with-tclinclude={ TclPackage().include_directories[0]}',
                f'--with-tk={ TkPackage().install_directory / "Library" / "Frameworks" / "Tk.framework"}',
                f'--with-tkinclude={ TkPackage().include_directories[0]}',
            ]
        else:
            args += [
                f'--with-tcl={ TclPackage().install_directory / "lib" }',
                f'--with-tk={ TkPackage().install_directory / "lib" }',
                '--with-Xmu',
            ]
        return args
# # Remove the GL directory provided by Togl and link to the OS X
# # OpenGL framework header directory instead.
# togl_gl_dir = os.path.join(togl_src_dir, 'GL')
# shutil.rmtree(togl_gl_dir)
# os.symlink(os.path.join(SDKROOT, 'System', 'Library', 'Frameworks', 'OpenGL.framework', 'Headers'), togl_gl_dir)


class DbPackage(InstallInConquestPythonBaseMixin, MakeInstallMixin, Package):
    '''AKA BSDDb. This is made by Oracle now. So, DO NOT update this version.'''
    name = 'db'
    version = '5.3.28'

    @property
    def source_archives(self):
        return {
            f'db-{self.version}.tar.gz': f'https://download.oracle.com/berkeley-db/db-{self.version}.tar.gz'
        }

    def patch_sources(self):
        # Fails to build on recent Clang and gcc versions without this patch.
        # See https://github.com/narkoleptik/os-x-berkeleydb-patch
        self.patch(
            self.main_source_directory_path / 'src' / 'dbinc' / 'atomic.h',
            ('\t__atomic_compare_exchange((p), (o), (n))',
                '\t__atomic_compare_exchange_db((p), (o), (n))'),
            ('static inline int __atomic_compare_exchange(',
                'static inline int __atomic_compare_exchange_db(')
        )

    @property
    def configuration_script(self):
        return self.main_source_directory_path / 'dist' / 'configure'

    @property
    def arguments_to_configuration_script(self):
        return super().arguments_to_configuration_script + [
            '--enable-compat185',
            '--enable-shared',
            '--enable-dbm'
        ]


class JpegPackage(InstallInConquestPythonBaseMixin, AutoconfMixin, Package):
    name = 'jpeg'
    version = '9d'

    @property
    def source_archives(self):
        return {
            f'jpegsrc.v{self.version}.tar.gz': f'http://jpegclub.org/reference/wp-content/uploads/2020/01/jpegsrc.v9d.tar.gz'
        }


class ConquestPythonPackage(AutoconfMixin, MakeInstallMixin, Package):
    name = 'conquest_python'
    version = '2.7.17-1'
    python_version = '2.7.17'

    @property
    def source_archives(self):
        return {
            f'Python-{self.python_version}.tar.xz': f'https://www.python.org/ftp/python/{self.python_version}/Python-{self.python_version}.tar.xz'
        }

    def patch_sources(self):
        if mac:
            self.patch(
                self.main_source_directory_path / 'Modules' / 'Setup.dist',
                ('#SSL=/usr/local/ssl',
                 f'SSL={OpensslPackage().install_directory}'),
                ('#_ssl _ssl.c \\', '_ssl _ssl.c \\'),
                ('#\t-DUSE_SSL -I$(SSL)/include -I$(SSL)/include/openssl \\',
                 '-DUSE_SSL -I$(SSL)/include -I$(SSL)/include/openssl \\'),
                ('#\t-L$(SSL)/lib -lssl -lcrypto', '-L$(SSL)/lib -lssl -lcrypto')
            )
        else:
            self.patch(
                self.main_source_directory_path / 'setup.py',
                ('/usr/contrib/ssl/include/',
                 f'{OpensslPackage().install_directory}/include'),
                ('/usr/contrib/ssl/lib/',
                 f'{OpensslPackage().install_directory}/lib'),
            )

    @property
    def main_source_directory_path(self):
        return self.source_extracted / f'Python-{self.python_version}'

    # Todo, might be required in cppflags
    @property
    def cflags(self):
        cflags = super().cflags + [
            f'-I{SqlitePackage().include_directories[0]}',
            f'-I{OpensslPackage().include_directories[0]}',
        ]
        if mac:
            cflags.append(f'-I{SDKROOT}/usr/include')
        else:
            cflags.append('-fPIC')

        return cflags

    @property
    def ldflags(self):
        ldflags = super().ldflags + [
            f'-L{SqlitePackage().library_link_directories[0]}',
            f'-L{OpensslPackage().library_link_directories[0]}',
            '-lsqlite3',
            '-lssl',
            '-lcrypto'
        ]
        if mac:
            ldflags += [
            ]
            ldflags.append(f'-I{SDKROOT}/usr/include')
        else:
            wanted_rpath = ':'.join(str(x) for x in
                                    SqlitePackage().library_link_directories
                                    + OpensslPackage().library_link_directories
                                    + self.library_link_directories
                                    # + DbPackage().library_link_directories
                                    )
            ldflags.append(f'-Wl,-rpath={wanted_rpath}')

        return ldflags

    @property
    def arguments_to_configuration_script(self):
        args = super().arguments_to_configuration_script
        args += [
            '--enable-optimizations',
            '--with-lto',
        ]
        if mac:
            frameworks_directory = self.install_directory / "Library" / "Frameworks"
            args += [
                f'--enable-framework={self.install_directory / "Library" / "Frameworks"}',
                f'--with-tcltk-includes=-I{TclPackage().include_directories[0]} -I{TkPackage().include_directories[0]}',
                f'--with-tcltk-libs=-F{frameworks_directory} -framework Tcl -framework Tk',
            ]
        else:
            args += [
                '--disable-ipv6',
                '--enable-unicode=ucs4',
                '--enable-shared',
            ]
        return args

    @property
    def python_base_directory(self):
        '''On MacOS, we must use what goes inside the framework as a base directory'''
        if mac:
            return self.install_directory / 'Library' / 'Frameworks' / 'Python.framework' / 'Versions' / '2.7'
        return self.install_directory

    @property
    def python_exe(self):
        return self.python_base_directory / 'bin' / 'python'

    def ensure_pip(self):
        self.system([str(self.python_exe), '-m', 'ensurepip'])
        self.system([str(self.python_exe), '-m', 'pip', 'install',
                     '--upgrade', 'pip', 'setuptools'], append_log=True)

    def pip_install(self, *args):
        self.system([str(self.python_exe), '-m', 'pip',
                     'install'] + [arg for arg in args])


#     def verify(self):
#         python_exe = self.python_exe(config)

#         test_scripts = ['''
# import sys, os
# try:
#     import Tkinter
# except ImportError:
#     import tkinter as Tkinter
# if sys.platform != "darwin" and "DISPLAY" in os.environ:
#     Tkinter.Tk()
# ''',
#                         '''
# import sqlite3
# import distutils.version
# # Ensure we haven't inadvertently got the (ancient) system SQLite
# assert distutils.version.LooseVersion('3.7.4') <= distutils.version.LooseVersion(sqlite3.sqlite_version)
# sqlite3.connect(":memory:")
# ''',
#                         ]

#         for s in test_scripts:
#             tempd = tempfile.mkdtemp()
#             try:
#                 tempf = os.path.join(tempd, 'test.py')
#                 with open(tempf, 'w') as f:
#                     f.write(s)
#                 subprocess.check_call(
#                     ' '.join([python_exe, tempf]), shell=True)
#             finally:
#                 shutil.rmtree(tempd)

######################################################################

class ApswPackage(Package):
    name = 'apsw'
    version = '3.31.1-r1'

    @property
    def source_archives(self):
        return {
            f'{self.name}-{self.version}.zip': f'https://github.com/rogerbinns/apsw/releases/download/{self.version}/{self.name}-{self.version}.zip'
        }

def main():
    try:
        shutil.rmtree(ConquestPythonPackage().install_directory)
    except OSError:
        pass
    ZlibPackage().build()
    SqlitePackage().build()
    OpensslPackage().build()
    TclPackage().build()
    TkPackage().build()
    ToglPackage().build()
    JpegPackage().build()
    DbPackage().build()
    # The items above must be installed before python
    ConquestPythonPackage().build()
    ConquestPythonPackage().ensure_pip()
    ConquestPythonPackage().pip_install(
        'Pmw==2.0.1',
        'numpy==1.16.6',
        'PyInstaller==3.5',
        'PyOpenGL==3.1.0',
        'nose==1.3.7',
        'Pillow==6.2.2',
        'nose-parameterized==0.6.0')
    ConquestPythonPackage().pip_install(
        'bsddb3==6.2.6',
        f'--install-option=--berkeley-db={ConquestPythonPackage().python_base_directory}',
        f'--install-option=--lflags=-L{ConquestPythonPackage().python_base_directory}/lib')
    ConquestPythonPackage().pip_install(
        'https://github.com/rogerbinns/apsw/releases/download/3.31.1-r1/apsw-3.31.1-r1.zip',
        '--global-option=fetch', '--global-option=--version', '--global-option=3.31.1', '--global-option=--all',
        '--global-option=build', '--global-option=--enable-all-extensions'
    )

if __name__ == "__main__":
    main()
