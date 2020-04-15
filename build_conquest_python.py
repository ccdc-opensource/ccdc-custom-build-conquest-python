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
        return super().arguments_to_configuration_script + ['--static']


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
            '-DSQLITE_ENABLE_FTS3_PARENTHESIS',
            '-DSQLITE_ENABLE_FTS4',
            '-DSQLITE_ENABLE_FTS5',
            '-DSQLITE_ENABLE_EXPLAIN_COMMENTS',
            '-DSQLITE_ENABLE_NULL_TRIM',
            '-DSQLITE_MAX_COLUMN=10000',
            '-DSQLITE_ENABLE_JSON1',
            '-DSQLITE_ENABLE_RTREE',
            '-DSQLITE_TCL=0',
        ]

    @property
    def ldflags(self):
        return super().ldflags + [
            '-lm'
        ]

    @property
    def arguments_to_configuration_script(self):
        return super().arguments_to_configuration_script + [
            '--enable-threadsafe',
            '--enable-shared=no',
            '--enable-static=yes',
            '--disable-readline',
            '--disable-dependency-tracking',
        ]

class OpensslPackage(InstallInConquestPythonBaseMixin, AutoconfMixin, Package):
    ''' Most of these settings have been based on the Homebrew Formula that can be found here for reference
    https://github.com/Homebrew/homebrew-core/blob/5ab9766e70776ef1702f8d40c8ef5159252c31be/Formula/openssl%401.1.rb
    more details were pilfered from Python.org's installer creation script
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
        # python build needs .a files in a directory away from .dylib
        # TODO: this might be unnecessary
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

# This can get very messy, very quickly, as I found out by following our custom scripts
# So take a look here for inspiration
# https://github.com/python/cpython/blob/2.7/Mac/BuildScript/build-installer.py
class TclPackage(AutoconfMixin, Package):
    name = 'tcl'
    version = '8.6.10'
    tclversion = '8.6'

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
    def install_directory(self):
        # On mac, this is not required, as all libraries are installed in the python framework
        if mac:
            return super().install_directory
        # On Linux, we install inside python
        return ConquestPythonPackage().python_base_directory

    @property
    def cflags(self):
        return super().cflags + [
            '-DNDEBUG'
        ]

    @property
    def configuration_script(self):
        return self.main_source_directory_path / 'unix' / 'configure'

    @property
    def arguments_to_configuration_script(self):
        args = super().arguments_to_configuration_script + [
            '--enable-shared',
            '--enable-threads',
            '--enable-64bit',
        ]
        if mac:
            args.extend([
                f'--libdir={ConquestPythonPackage().python_base_directory / "lib"}',
            ])
        return args

    def run_build_command(self):
        if mac:
            self.system([
                'make',
                f'TCL_LIBRARY="{ ConquestPythonPackage().python_base_directory / "lib" / "tcl8.6" }"',
                f'-j{multiprocessing.cpu_count()}'
                ],
                    env=self.environment_for_build_command, cwd=self.build_directory_path)
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
        return [self.install_directory / 'include']

    @property
    def bindir(self):
        return self.install_directory / "bin"

    @property
    def tclsh(self):
        return self.bindir / f"tclsh{ self.tclversion }"

    def run_install_command(self):
        if mac:
            self.system([
                'make',
                'install',
                f'TCL_LIBRARY="{ConquestPythonPackage().python_base_directory / "lib" / "tcl8.6"}"',
                f'PACKAGE_DIR={ ConquestPythonPackage().python_base_directory / "lib" / "tcl8.6" }',
            ],
                    env=self.environment_for_build_command, cwd=self.build_directory_path)
            try:
                os.unlink(self.bindir/'tclsh')
            except OSError:
                pass
            os.symlink(self.bindir /'tclsh8.6', self.bindir/'tclsh')
            # # copy msgcat.tcl because pyinstaller won't pick up modules
            # shutil.copytree(
            #     self.main_source_directory_path / 'library' / 'msgcat',
            #     self.install_directory /
            #     'Library' / 'Frameworks' / 'Tcl.framework' / 'Resources' / 'Scripts' / 'msgcat'
            # )
        else:
            super().run_install_command()

    def verify(self):
        honk_proc = subprocess.Popen([self.tclsh], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        honk_proc.stdin.write("puts honk\n".encode('utf-8'))
        out = honk_proc.communicate()
        honk_proc.stdin.close()
        s0 = out[0].decode().rstrip()
        if s0 !='honk':
            print(f'{self.tclsh} won\'t honk, stdout[{out[0].decode()}] stderr[{out[1].decode()}]')
            return False
        return True


class TkPackage(AutoconfMixin, Package):
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
        env['PATH']= f"{TclPackage().bindir}:{env['PATH']}"
        if mac:
            env['ac_cv_path_tclsh'] = f'{TclPackage().bindir / "tclsh8.6"}'
        return env

    @property
    def configuration_script(self):
        return self.main_source_directory_path / 'unix' / 'configure'

    @property
    def install_directory(self):
        return TclPackage().install_directory

    @property
    def arguments_to_configuration_script(self):
        if mac:
            return super().arguments_to_configuration_script + [
                f'--with-tcl={ ConquestPythonPackage().python_base_directory / "lib" }',
                '--enable-aqua',
                '--enable-shared',
                '--enable-threads',
                '--enable-64bit',
                f'--libdir={ConquestPythonPackage().python_base_directory / "lib"}',
            ]
        else:
            return super().arguments_to_configuration_script + [
                '--enable-shared',
                '--enable-threads',
                '--enable-64bit',
                f'--with-tcl={ TclPackage().install_directory / "lib" }'
            ]


    def run_build_command(self):
        if mac:
            self.system([
                'make',
                f'TCL_LIBRARY="{ ConquestPythonPackage().python_base_directory / "lib" / "tcl8.6" }"',
                f'TK_LIBRARY="{ ConquestPythonPackage().python_base_directory / "lib" / "tk8.6" }"',
                f'-j{multiprocessing.cpu_count()}'
                ],
                    env=self.environment_for_build_command, cwd=self.build_directory_path)
        else:
            super().run_build_command()

    def run_install_command(self):
        if mac:
            self.system([
                'make',
                'install',
                f'TCL_LIBRARY="{ConquestPythonPackage().python_base_directory / "lib" / "tcl8.6"}"',
                f'TK_LIBRARY="{ConquestPythonPackage().python_base_directory / "lib" / "tk8.6"}"',
            ],
                    env=self.environment_for_build_command, cwd=self.build_directory_path)

        else:
            super().run_install_command()

    @property
    def include_directories(self):
        '''Return the directories clients must add to their include path'''
        return [self.install_directory / 'include']

    def verify(self):
        itcl_check = '''
package require Itcl
package require Tk
puts "OK"
exit
'''
        itcl_proc = subprocess.Popen([TclPackage().tclsh], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        itcl_proc.stdin.write(itcl_check.encode('utf-8'))
        out = itcl_proc.communicate()
        itcl_proc.stdin.close()
        s0 = out[1].decode().rstrip()
        if "can't find package" in s0:
            print(f'{TclPackage().tclsh} won\'t do, stdout[{out[0].decode()}] stderr[{out[1].decode()}]')
            return False

        return True


class ToglPackage(InstallInConquestPythonBaseMixin, AutoconfMixin, Package):
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
    def install_directory(self):
        return TclPackage().install_directory

    @property
    def build_directory_path(self):
        '''The autoconf script is a bit rubbish, only works in-source :('''
        return self.main_source_directory_path


    @property
    def arguments_to_configuration_script(self):
        args = super().arguments_to_configuration_script
        if mac:
            args += [
                f'--with-tcl={ ConquestPythonPackage().python_base_directory / "lib" }',
                f'--libdir={ConquestPythonPackage().python_base_directory / "lib"}',
                f'--with-tclinclude={ TclPackage().include_directories[0]}',
                f'--with-tk={ ConquestPythonPackage().python_base_directory / "lib" }',
                f'--with-tkinclude={ TkPackage().include_directories[0]}',
            ]
        else:
            args += [
                f'--with-tcl={ TclPackage().install_directory / "lib" }',
                f'--with-tk={ TkPackage().install_directory / "lib" }',
                '--with-Xmu',
            ]
        return args

    def verify(self):
        itcl_check = '''
package require Togl
wm title . "Togl runs"
togl .o1 -width 200 -height 200 -rgba true -double true -depth true -create double::create_cb -display double::display_cb -reshape double::reshape_cb -multisample false -ident Aliased  
puts "OK"
exit
'''
        itcl_proc = subprocess.Popen([TclPackage().tclsh], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        itcl_proc.stdin.write(itcl_check.encode('utf-8'))
        out = itcl_proc.communicate()
        itcl_proc.stdin.close()
        s0 = out[1].decode().rstrip()
        if "can't find package" in s0:
            print(f'{TclPackage().tclsh} won\'t do, stdout[{out[0].decode()}] stderr[{out[1].decode()}]')
            return False

        return True



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
        ldflags = super().ldflags
        wanted_rpath = ':'.join(str(x) for x in
                                SqlitePackage().library_link_directories
                                + OpensslPackage().library_link_directories
                                + self.library_link_directories
                                # + DbPackage().library_link_directories
                                )
        if mac:
            ldflags.extend([
                f'-rpath {wanted_rpath}',
            ]
        else:
            ldflags.extend([
                f'-L{SqlitePackage().library_link_directories[0]}',
                f'-L{OpensslPackage().library_link_directories[0]}',
                '-lsqlite3',
                '-lssl',
                '-lcrypto',
                f'-Wl,-rpath={wanted_rpath}',
            ]

        return ldflags

    @property
    def environment_for_configuration_script(self):
        env = super().environment_for_configuration_script
        if mac:
            env['DYLD_LIBRARY_PATH'] = f"{self.python_base_directory / 'lib'}"
        return env

    @property
    def arguments_to_configuration_script(self):
        args = super().arguments_to_configuration_script
        args += [
            '--enable-optimizations',
            '--with-lto',
            '--disable-ipv6',
            '--enable-unicode=ucs4',
        ]
        if mac:
            args += [
                f'--enable-framework={self.install_directory / "Library" / "Frameworks"}',
                # Tcl and Tk are on the same path
                f'--with-tcltk-includes=-I{TclPackage().include_directories[0]}',
                f'--with-tcltk-libs=-L{self.python_base_directory / "lib"}  -ltcl8.6 -ltk8.6',
                f"LDFLAGS={self.environment_for_configuration_script['LDFLAGS']}",
                f"CFLAGS={self.environment_for_configuration_script['CFLAGS']}",
                f"CPPFLAGS={self.environment_for_configuration_script['CFLAGS']}",
                f"DYLD_LIBRARY_PATH={self.python_base_directory / 'lib'}",
                f"PKG_CONFIG_PATH={self.python_base_directory / 'lib'/ 'pkgconfig'}",
            ]
        else:
            args += [
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

    def pip_install(self, *args, env=dict(os.environ)):
        self.system([str(self.python_exe), '-m', 'pip',
                     'install'] + [arg for arg in args], env=env)


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
    bdb_env=dict(os.environ)
    bdb_env['BERKELEYDB_DIR']=f'{ConquestPythonPackage().python_base_directory}'
    ConquestPythonPackage().pip_install('-v',
        'bsddb3==6.2.7',
        f'--install-option=--berkeley-db={ConquestPythonPackage().python_base_directory}',
        f'--install-option=--lflags=-L{ConquestPythonPackage().python_base_directory}/lib',
        env=bdb_env)
    ConquestPythonPackage().pip_install(
        'https://github.com/rogerbinns/apsw/releases/download/3.31.1-r1/apsw-3.31.1-r1.zip',
        '--global-option=fetch', '--global-option=--version', '--global-option=3.31.1', '--global-option=--all',
        '--global-option=build', '--global-option=--enable-all-extensions'
    )

if __name__ == "__main__":
    main()
