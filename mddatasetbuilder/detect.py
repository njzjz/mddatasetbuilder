"""Detect from trajectory."""

import pickle
from abc import ABCMeta, abstractmethod
from collections import defaultdict
from enum import Enum, auto
from typing import List, Optional, Tuple, Union, cast

import numpy as np
from ase import Atom, Atoms
from openbabel import openbabel

from mddatasetbuilder.dps import dps as connectmolecule


class Detect(metaclass=ABCMeta):
    """Detect structures from file(s)."""

    def __init__(self, filename, atomname, pbc, errorlimit=None, errorfilename=None):
        self.filename = filename
        self.atomname = atomname
        self.pbc = pbc
        self.errorlimit = errorlimit
        self.errorfilename = errorfilename
        self.steplinenum = self._readN()

    @abstractmethod
    def _readN(self) -> int:
        pass

    @abstractmethod
    def readatombondtype(self, item) -> Tuple[dict, int]:
        """Read bond types of atoms such as C1111."""
        pass

    @abstractmethod
    def readmolecule(self, lines) -> Tuple[List[List[int]], Optional[Atoms]]:
        """Read molecules."""
        pass

    @staticmethod
    def gettype(inputtype):
        """Get the class for the input file type."""
        if inputtype == "bond":
            detectclass = DetectBond
        elif inputtype == "dump":
            detectclass = DetectDump
        else:
            raise RuntimeError("Wrong input file type")
        return detectclass


class DetectBond(Detect):
    """Detect from the LAMMPS bond file."""

    def _readN(self):
        """Read bondfile N, which should be at very beginning."""
        N = None
        atomtype = None
        stepaindex = None
        stepbindex = None
        # copy from reacnetgenerator on 2018-12-15
        with open(
            self.filename if isinstance(self.filename, str) else self.filename[0]
        ) as f:
            iscompleted = False
            for index, line in enumerate(f):
                if line.startswith("#"):
                    if line.startswith("# Number of particles"):
                        if iscompleted:
                            stepbindex = index
                            break
                        else:
                            iscompleted = True
                            stepaindex = index
                        N = [int(s) for s in line.split() if s.isdigit()][0]
                        atomtype = np.zeros(N, dtype=int)
                else:
                    s = line.split()
                    assert atomtype is not None
                    atomtype[int(s[0]) - 1] = int(s[1])
        if stepaindex is None or stepbindex is None or N is None or atomtype is None:
            raise RuntimeError("The bond file is not completed")
        steplinenum = stepbindex - stepaindex
        self._N = N
        self.atomtype = atomtype
        self.atomnames = self.atomname[self.atomtype - 1]
        return steplinenum

    def readatombondtype(self, item):
        """Read bond orders of atoms.

        Parameters
        ----------
        item : tuple
            (step, lines), _

        Returns
        -------
        dict
            dict of bond orders
        int
            the step index
        """
        # copy from reacnetgenerator on 2018-12-15
        (step, lines), _ = item
        d = defaultdict(list)
        for line in lines:
            if line:
                if line[0] != "#":
                    s = line.split()
                    atombond = sorted(
                        max(1, round(float(x)))
                        for x in s[4 + int(s[2]) : 4 + 2 * int(s[2])]
                    )
                    d[pickle.dumps((self.atomnames[int(s[0]) - 1], atombond))].append(
                        int(s[0])
                    )
        return d, step

    def readmolecule(self, lines) -> Tuple[List[List[int]], Optional[Atoms]]:
        """Return molecules from lines.

        Parameters
        ----------
        lines : list of strs
            Lines of LAMMPS bond files.

        Returns
        -------
        molecules: list
            Indexes of atoms in molecules.
        None
            None
        """
        # copy from reacnetgenerator on 2018-12-15
        bond: List[Optional[List[int]]] = [None] * self._N
        for line in lines:
            if line:
                if not line.startswith("#"):
                    s = line.split()
                    bond[int(s[0]) - 1] = [int(x) - 1 for x in s[3 : 3 + int(s[2])]]
        bond_ = cast(List[List[int]], bond)
        molecules = connectmolecule(bond_)
        return molecules, None


class DetectDump(Detect):
    """Detect from the dump file."""

    def _readN(self):
        # copy from reacnetgenerator on 2018-12-15
        iscompleted = False
        N = None
        atomtype = None
        stepaindex = None
        stepbindex = None
        with open(
            self.filename if isinstance(self.filename, str) else self.filename[0]
        ) as f:
            linecontent = None
            for index, line in enumerate(f):
                if line.startswith("ITEM:"):
                    linecontent = self.LineType.linecontent(line)
                    if linecontent == self.LineType.ATOMS:
                        keys = line.split()
                        self.id_idx = keys.index("id") - 2
                        self.tidx = keys.index("type") - 2
                        self.xidx = keys.index("x") - 2
                        self.yidx = keys.index("y") - 2
                        self.zidx = keys.index("z") - 2
                else:
                    if linecontent is None:
                        raise RuntimeError("No ITEM: in the dump file")
                    elif linecontent == self.LineType.NUMBER:
                        if iscompleted:
                            stepbindex = index
                            break
                        else:
                            iscompleted = True
                            stepaindex = index
                        N = int(line.split()[0])
                        atomtype = np.zeros(N, dtype=int)
                    elif linecontent == self.LineType.ATOMS:
                        s = line.split()
                        assert atomtype is not None
                        atomtype[int(s[self.id_idx]) - 1] = int(s[self.tidx])
        if stepaindex is None or stepbindex is None or N is None or atomtype is None:
            raise RuntimeError("The dump file is not completed")
        steplinenum = stepbindex - stepaindex
        self._N = N
        self.atomtype = atomtype
        self.atomnames = self.atomname[self.atomtype - 1]
        return steplinenum

    def readatombondtype(self, item):
        """Read bond orders of atoms.

        Parameters
        ----------
        item : tuple
            (step, lines), _

        Returns
        -------
        dict
            dict of bond orders
        int
            the step index
        """
        (step, lines), needlerror = item
        lerror: Optional[Union[np.ndarray, List[float]]] = None
        d = defaultdict(list)
        step_atoms, ids = self.readcrd(lines)
        if needlerror:
            trajline, errorline = lines
            lerror = np.fromstring(errorline, dtype=float, sep=" ")[7:]
            lerror = [x for (y, x) in sorted(zip(ids, lerror))]
        level = self._crd2bond(step_atoms, readlevel=True)
        for i, (n, l) in enumerate(zip(self.atomnames, level)):
            if lerror is None or (
                self.errorlimit is not None and lerror[i] > self.errorlimit
            ):
                # Note that atom id starts from 1
                d[pickle.dumps((n, sorted(l)))].append(i + 1)
        return d, step

    def readmolecule(self, lines) -> Tuple[List[List[int]], Optional[Atoms]]:
        """Return molecules from lines.

        Parameters
        ----------
        lines : list of strs
            Lines of LAMMPS bond files.

        Returns
        -------
        molecules: list
            Indexes of atoms in molecules.
        step_atoms: ase.Atoms
            The atoms of the frame.
        """
        step_atoms, _ = self.readcrd(lines)
        bond = self._crd2bond(step_atoms, readlevel=False)
        molecules = connectmolecule(bond)
        # return atoms as well
        return molecules, step_atoms

    @classmethod
    def _crd2bond(cls, step_atoms, readlevel):
        # copy from reacnetgenerator on 2019/4/13
        # updated on 2019/10/11
        atomnumber = len(step_atoms)
        # Use openbabel to connect atoms
        mol = openbabel.OBMol()
        mol.BeginModify()
        for idx, (num, position) in enumerate(
            zip(step_atoms.get_atomic_numbers(), step_atoms.positions)
        ):
            a = mol.NewAtom(idx)
            a.SetAtomicNum(int(num))
            a.SetVector(*position)
        # Apply period boundry conditions
        # openbabel#1853, supported in v3.1.0
        if step_atoms.pbc.any():
            cell = step_atoms.cell
            uc = openbabel.OBUnitCell()
            uc.SetData(
                openbabel.vector3(cell[0][0], cell[0][1], cell[0][2]),
                openbabel.vector3(cell[1][0], cell[1][1], cell[1][2]),
                openbabel.vector3(cell[2][0], cell[2][1], cell[2][2]),
            )
            mol.CloneData(uc)
            mol.SetPeriodicMol()
        mol.ConnectTheDots()
        # when readlevel is False, bond is used to store connected atoms
        # otherwise, bondlevel is used to store bond orders
        bond = [[] for i in range(atomnumber)]
        if readlevel:
            mol.PerceiveBondOrders()
        mol.EndModify()
        for b in openbabel.OBMolBondIter(mol):
            s1 = b.GetBeginAtom().GetId()
            s2 = b.GetEndAtom().GetId()
            if not readlevel:
                bond[s1].append(s2)
                bond[s2].append(s1)
            else:
                level = b.GetBondOrder()
                bond[s1].append(level)
                bond[s2].append(level)
        return bond

    def readcrd(self, item) -> Tuple[Atoms, List[int]]:
        """Only this function can read coordinates."""
        lines = item
        # box information
        ss = []
        step_atoms = []
        ids = []
        linecontent = None
        for line in lines:
            if line:
                if line.startswith("ITEM:"):
                    linecontent = self.LineType.linecontent(line)
                else:
                    if linecontent is None:
                        raise RuntimeError("No ITEM: in the dump file")
                    elif linecontent == self.LineType.ATOMS:
                        s = line.split()
                        ids.append(int(s[self.id_idx]))
                        step_atoms.append(
                            Atom(
                                self.atomname[int(s[self.tidx]) - 1],
                                (
                                    float(s[self.xidx]),
                                    float(s[self.yidx]),
                                    float(s[self.zidx]),
                                ),
                            )
                        )
                    elif linecontent == self.LineType.BOX:
                        s = line.split()
                        ss.append(list(map(float, s)))
        # box information to 3x3 cell
        ss = np.array(ss)
        if ss.shape[1] > 2:
            xy = ss[0][2]
            xz = ss[1][2]
            yz = ss[2][2]
        else:
            xy, xz, yz = 0.0, 0.0, 0.0
        xlo = ss[0][0] - min(0.0, xy, xz, xy + xz)
        xhi = ss[0][1] - max(0.0, xy, xz, xy + xz)
        ylo = ss[1][0] - min(0.0, yz)
        yhi = ss[1][1] - max(0.0, yz)
        zlo = ss[2][0]
        zhi = ss[2][1]
        boxsize = np.array(
            [[xhi - xlo, 0.0, 0.0], [xy, yhi - ylo, 0.0], [xz, yz, zhi - zlo]]
        )
        # sort by ID
        step_atoms_ = [x for (y, x) in sorted(zip(ids, step_atoms))]
        step_atoms = Atoms(step_atoms_, cell=boxsize, pbc=self.pbc)
        return step_atoms, ids

    class LineType(Enum):
        """Line type in the LAMMPS dump files."""

        TIMESTEP = auto()
        ATOMS = auto()
        NUMBER = auto()
        BOX = auto()
        OTHER = auto()

        @classmethod
        def linecontent(cls, line):
            """Return line content."""
            if line.startswith("ITEM: TIMESTEP"):
                return cls.TIMESTEP
            if line.startswith("ITEM: ATOMS"):
                return cls.ATOMS
            if line.startswith("ITEM: NUMBER OF ATOMS"):
                return cls.NUMBER
            if line.startswith("ITEM: BOX"):
                return cls.BOX
            return cls.OTHER
