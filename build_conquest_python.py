#!/usr/bin/env python3

import sys
import subprocess
import os
import shutil
import tempfile
import multiprocessing

from pathlib import Path
from ccdc.thirdparty.package import Package, AutoconfMixin, MakeInstallMixin, NoArchiveMixin


class InstallInConquestPythonBaseMixin(object):
    @property
    def install_directory(self):
        '''The nuance with descendants of this class is that these libraries will be installed under the Python Framework on MacOS'''
        return ConquestPythonPackage().python_base_directory


class ZlibPackage(InstallInConquestPythonBaseMixin, AutoconfMixin, NoArchiveMixin, Package):
    '''Zlib'''
    name = 'zlib'
    version = '1.2.11'

    @property
    def source_archives(self):
        return {
            f'zlib-{self.version}.tar.xz': f'https://www.zlib.net/zlib-{self.version}.tar.xz'
        }


class SqlitePackage(InstallInConquestPythonBaseMixin, AutoconfMixin, NoArchiveMixin, Package):
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


class OpensslPackage(InstallInConquestPythonBaseMixin, AutoconfMixin, NoArchiveMixin, Package):
    ''' Most of these settings have been based on the Homebrew Formula that can be found here for reference
    https://github.com/Homebrew/homebrew-core/blob/5ab9766e70776ef1702f8d40c8ef5159252c31be/Formula/openssl%401.1.rb
    more details were pilfered from Python.org's installer creation script
    '''
    name = 'openssl'
    version = '1.1.1g'

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
        if self.macos:
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
        # env = self.environment_for_configuration_script
        # self.system(
        #     ['make', 'test'],
        #     env=env, cwd=self.build_directory_path)
        pass

# This can get very messy, very quickly, as I found out by following our custom scripts
# So take a look here for inspiration
# https://github.com/python/cpython/blob/2.7/Mac/BuildScript/build-installer.py


class TclPackage(AutoconfMixin, NoArchiveMixin, Package):
    name = 'tcl'
    version = '8.6.10'
    tclversion = '8.6'

    @property
    def source_archives(self):
        return {
            # Canonica would be https://prdownloads.sourceforge.net/tcl but it's fetching truncated files 
            f'tcl{self.version}-src.tar.gz': f'https://ftp.osuosl.org/pub/blfs/conglomeration/tcl/tcl{self.version}-src.tar.gz'
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
        if self.macos:
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
        if self.macos:
            args.extend([
                f'--libdir={ConquestPythonPackage().python_base_directory / "lib"}',
            ])
        return args

    def run_build_command(self):
        if self.macos:
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
        if self.macos:
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
            os.symlink(self.bindir / 'tclsh8.6', self.bindir/'tclsh')
            # # copy msgcat.tcl because pyinstaller won't pick up modules
            # shutil.copytree(
            #     self.main_source_directory_path / 'library' / 'msgcat',
            #     self.install_directory /
            #     'Library' / 'Frameworks' / 'Tcl.framework' / 'Resources' / 'Scripts' / 'msgcat'
            # )
        else:
            super().run_install_command()

    def verify(self):
        honk_proc = subprocess.Popen(
            [self.tclsh], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        honk_proc.stdin.write("puts honk\n".encode('utf-8'))
        out = honk_proc.communicate()
        honk_proc.stdin.close()
        s0 = out[0].decode().rstrip()
        if s0 != 'honk':
            print(
                f'{self.tclsh} won\'t honk, stdout[{out[0].decode()}] stderr[{out[1].decode()}]')
            return False
        return True


class TkPackage(AutoconfMixin, NoArchiveMixin, Package):
    name = 'tk'
    version = '8.6.10'

    @property
    def source_archives(self):
        return {
            # Canonical would be https://prdownloads.sourceforge.net/tcl/ but it's fetching garbage
            f'tk{self.version}-src.tar.gz': f'https://fossies.org/linux/misc/tk{self.version}-src.tar.gz'
        }

    @property
    def main_source_directory_path(self):
        return self.source_extracted / f'{self.name}{self.version}'

    @property
    def environment_for_configuration_script(self):
        env = super().environment_for_configuration_script
        env['PATH'] = f"{TclPackage().bindir}:{env['PATH']}"
        if self.macos:
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
        if self.macos:
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
        if self.macos:
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
        if self.macos:
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
        itcl_proc = subprocess.Popen([TclPackage(
        ).tclsh], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        itcl_proc.stdin.write(itcl_check.encode('utf-8'))
        out = itcl_proc.communicate()
        itcl_proc.stdin.close()
        s0 = out[1].decode().rstrip()
        if "can't find package" in s0:
            print(
                f'{TclPackage().tclsh} won\'t do, stdout[{out[0].decode()}] stderr[{out[1].decode()}]')
            return False

        return True


class ToglPackage(InstallInConquestPythonBaseMixin, AutoconfMixin, NoArchiveMixin, Package):
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
        if self.macos:
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
        itcl_proc = subprocess.Popen([TclPackage(
        ).tclsh], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        itcl_proc.stdin.write(itcl_check.encode('utf-8'))
        out = itcl_proc.communicate()
        itcl_proc.stdin.close()
        s0 = out[1].decode().rstrip()
        if "can't find package" in s0:
            print(
                f'{TclPackage().tclsh} won\'t do, stdout[{out[0].decode()}] stderr[{out[1].decode()}]')
            return False

        return True


class DbPackage(InstallInConquestPythonBaseMixin, MakeInstallMixin, NoArchiveMixin, Package):
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


class JpegPackage(InstallInConquestPythonBaseMixin, AutoconfMixin, NoArchiveMixin, Package):
    name = 'jpeg'
    version = '9d'

    @property
    def source_archives(self):
        return {
            f'jpegsrc.v{self.version}.tar.gz': f'http://jpegclub.org/reference/wp-content/uploads/2020/01/jpegsrc.v9d.tar.gz'
        }


class ConquestPythonPackage(AutoconfMixin, MakeInstallMixin, Package):
    name = 'conquest_python'
    version = '2.7.18'

    @property
    def source_archives(self):
        return {
            f'Python-{self.version}.tar.xz': f'https://www.python.org/ftp/python/{self.version}/Python-{self.version}.tar.xz'
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
        return self.source_extracted / f'Python-{self.version}'

    # Todo, might be required in cppflags
    @property
    def cflags(self):
        cflags = super().cflags + [
            f'-I{SqlitePackage().include_directories[0]}',
            f'-I{OpensslPackage().include_directories[0]}',
        ]
        if self.macos:
            cflags.append(f'-I{self.macos_sdkroot}/usr/include')
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
        if self.macos:
            ldflags.extend([
                f'-rpath {wanted_rpath}',
            ])
        else:
            ldflags.extend([
                f'-L{SqlitePackage().library_link_directories[0]}',
                f'-L{OpensslPackage().library_link_directories[0]}',
                '-lsqlite3',
                '-lssl',
                '-lcrypto',
                f'-Wl,-rpath={wanted_rpath}',
            ])

        return ldflags

    @property
    def environment_for_configuration_script(self):
        env = super().environment_for_configuration_script
        if self.macos:
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
        if self.macos:
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
        if self.macos:
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

    # not building archive, this will come later
    def build(self):
        self.cleanup()
        self.fetch_source_archives()
        self.extract_source_archives()
        self.patch_sources()
        self.run_configuration_script()
        self.run_build_command()
        self.run_install_command()
        self.verify()


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
    bdb_env = dict(os.environ)
    bdb_env['BERKELEYDB_DIR'] = f'{ConquestPythonPackage().python_base_directory}'
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
    ConquestPythonPackage().create_archive()


if __name__ == "__main__":
    main()
