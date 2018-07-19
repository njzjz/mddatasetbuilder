#MDDatasetMaker
#Author: Jinzhe Zeng
#Email: njzjz@qq.com 10154601140@stu.ecnu.edu.cn
import itertools
import numpy as np
import os
import shutil
from ReacNetGenerator import ReacNetGenerator

class DatasetMaker(object):
    def __init__(self,atomname=["C","H","O"],clusteratom=["C","H","O"],n_eachspecies=10,bondfilename="bonds.reaxc",dumpfilename="dump.ch4",moleculefilename=None,tempfilename=None,dataset_dir="dataset",xyzfilename="md"):
        print("MDDatasetMaker")
        print("Author: Jinzhe Zeng")
        print("Email: njzjz@qq.com 10154601140@stu.ecnu.edu.cn")
        self.dumpfilename=dumpfilename
        self.bondfilename=bondfilename
        self.moleculefilename=moleculefilename if moleculefilename else self.bondfilename+".moname"
        self.tempfilename=tempfilename if tempfilename else self.bondfilename+".temp2"
        self.dataset_dir=dataset_dir
        self.xyzfilename=xyzfilename
        self.n_eachspecies=n_eachspecies
        self.atomname=np.array(atomname)
        self.clusteratom=clusteratom
        self.dataset={}
        self.atombondtype=[]
        self.trajatom_dir="trajatom"
        self.ReacNetGenerator=ReacNetGenerator(atomname=self.atomname,runHMM=False,inputfilename=self.bondfilename,moleculefilename=self.moleculefilename,moleculetemp2filename=self.tempfilename)
        self.nuclearcharge={"H":1,"He":2,"Li":3,"Be":4,"B":5,"C":6,"N":7,"O":8,"F":9,"Ne":10}

    def makedataset(self,processtraj=True):
        if processtraj:
            self.ReacNetGenerator.inputfilename=self.bondfilename
            self.ReacNetGenerator.step1()
            self.ReacNetGenerator.step2()
            if self.ReacNetGenerator.SMILES:
                self.ReacNetGenerator.printmoleculeSMILESname()
            else:
                self.ReacNetGenerator.printmoleculename()
        self.readlammpscrdN()
        #self.readmoname()
        #self.sorttrajatoms()
        self.writecoulumbmatrixs()

    def readmoname(self):
        if os.path.exists(self.trajatom_dir):
            shutil.rmtree(self.trajatom_dir)
        os.makedirs(self.trajatom_dir)
        with open(self.moleculefilename) as fm,open(self.tempfilename) as ft:
            for linem,linet in zip(fm,ft):
                sm=linem.split()
                st=linet.split()
                mname=sm[0]
                matoms=np.array([int(x) for x in sm[1].split(",")])
                mbonds=np.array([[int(y) for y in x.split(",")] for x in sm[2].split(";")]) if len(sm)==3 else np.array([])
                for atom in matoms:
                    if self.atomname[self.atomtype[atom]-1] in self.clusteratom:
                        atombond=[]
                        for bond in mbonds:
                            if bond[0]==atom or bond[1]==atom:
                                atombond.append(bond[2])
                        atombondstr="".join(str(x) for x in sorted(atombond))
                        if not self.atomname[self.atomtype[atom]-1]+atombondstr in self.atombondtype:
                            self.atombondtype.append(self.atomname[self.atomtype[atom]-1]+atombondstr)
                        with open(self.trajatom_dir+"/trajatom."+self.atomname[self.atomtype[atom]-1]+atombondstr,"a") as f:
                            print(atom,st[-1],file=f)
        with open("trajatom.list","w") as f:
            for atombondstr in  self.atombondtype:
                print(atombondstr,file=f)

    def sorttrajatom(self,trajatomfilename):
        dstep={}
        with open(self.trajatom_dir+"/trajatom."+trajatomfilename) as f:
            for line in f:
                s=line.split()
                steps=np.array([int(x) for x in s[-1].split(",")])
                for step in steps:
                    if step in dstep:
                        dstep[step].append(s[0])
                    else:
                        dstep[step]=[s[0]]
        with open(self.trajatom_dir+"/stepatom."+trajatomfilename,"w") as f:
            for step,atoms in dstep.items():
                print(step,",".join(atoms),file=f)

    def trajlist(self):
        with open("trajatom.list") as f:
            for line in f:
                yield line

    def sorttrajatoms(self):
        for line in self.trajlist():
            self.sorttrajatom(line.strip())

    def writecoulumbmatrixs(self):
        for line in self.trajlist():
            self.writecoulumbmatrix(line.strip())

    def readlammpscrdstep(self,item):
        (step,lines),_=item
        atomtype=np.zeros((self.ReacNetGenerator.N),dtype=np.int)
        atomcrd=np.zeros((self.ReacNetGenerator.N,3))
        boxsize=[]
        for line in lines:
            if line:
                if line.startswith("ITEM:"):
                    if line.startswith("ITEM: TIMESTEP"):
                        linecontent=4
                    elif line.startswith("ITEM: ATOMS"):
                        linecontent=3
                    elif line.startswith("ITEM: NUMBER OF ATOMS"):
                        linecontent=1
                    elif line.startswith("ITEM: BOX BOUNDS"):
                        linecontent=2
                else:
                    if linecontent==3:
                        s=line.split()
                        atomtype[int(s[0])-1]=int(s[1])
                        atomcrd[int(s[0])-1]=float(s[2]),float(s[3]),float(s[4])
                    elif linecontent==2:
                        s=line.split()
                        boxsize.append(float(s[1])-float(s[0]))
        return atomtype,atomcrd,np.array(boxsize)

    def readlammpscrdN(self):
        self.ReacNetGenerator.inputfilename=self.dumpfilename
        self.steplinenum=self.ReacNetGenerator.readlammpscrdN()
        self.N=self.ReacNetGenerator.N
        self.atomtype=self.ReacNetGenerator.atomtype

    def writecoulumbmatrix(self,trajatomfilename,cutoff=3.5):
        dstep={}
        with open(self.trajatom_dir+"/stepatom."+trajatomfilename) as f:
            for line in f:
                s=line.split()
                dstep[int(s[0])]=[int(x) for x in s[1].split(",")]
        with open(self.dumpfilename) as f,open(self.trajatom_dir+"/coulumbmatrix."+trajatomfilename,'w') as fm:
            for item in enumerate(itertools.islice(itertools.zip_longest(*[f]*self.steplinenum),0,None,1)):
                if item[0] in dstep:
                    atomtype,atomcrd,boxsize=self.readlammpscrdstep((item,None))
                    for atoma in dstep[item[0]]:
                        cutoffatoms=[]
                        for i in range(len(atomcrd)):
                            dxyz=atomcrd[atoma]-atomcrd[i]
                            dxyz=dxyz-np.round(dxyz/boxsize)*boxsize
                            if 0<np.linalg.norm(dxyz)<=cutoff:
                                cutoffatoms.append(i)
                        cutoffcrds=atomcrd[cutoffatoms]
                        for j in range(1,len(cutoffcrds)):
                            cutoffcrds[j]-=np.round((cutoffcrds[j]-atomcrd[i])/boxsize)*boxsize
                        print(item[0],atoma,",".join(str(x) for x in self.calcoulumbmatrix(atomtype[atoma],atomcrd[atoma],atomtype[cutoffatoms],cutoffcrds)),file=fm)

    def calcoulumbmatrix(self,atomtypea,atomcrda,atomtype,atomcrd):
        return np.sort([self.nuclearcharge[self.atomname[atomtype[i]-1]]/np.linalg.norm(atomcrd[i]-atomcrda) for i in range(len(atomcrd))])

if __name__ == '__main__':
    DatasetMaker(bondfilename="bonds.reaxc.ch4_new",dataset_dir="dataset_ch4",xyzfilename="ch4").makedataset(processtraj=False)
