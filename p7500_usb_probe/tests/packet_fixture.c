#include <stdio.h>
#include <stdlib.h>
#include "../native/read_packets.h"
int main(int argc,char**argv){if(argc!=5)return 2;unsigned char req[16];unsigned n=make_fixed_read(req,atoi(argv[1]),strtoul(argv[2],0,16),strtoul(argv[3],0,16),strtoul(argv[4],0,10));if(!n)return 3;for(unsigned i=0;i<n;i++)printf("%02x",req[i]);return 0;}
