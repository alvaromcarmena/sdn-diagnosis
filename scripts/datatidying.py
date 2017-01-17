import csv
import random

csvEntrada = csv.reader(open("bayesianNetwork.csv", "r"))
csvSalida = csv.writer(open("file.csv", "a"))
contador = 0
contador2 = 0
for line in csvEntrada:
    if "Normal_functioning" not in line:
        csvSalida.writerow(line)
    else:
        contador2 = contador2 + 1
        randomNumber = random.randrange(100)
        print(randomNumber)
        if randomNumber>50:
            csvSalida.writerow(line)
        else:
            contador = contador + 1

    print(contador," líneas Normal_functioning eliminadas de un total de: ",contador2)
