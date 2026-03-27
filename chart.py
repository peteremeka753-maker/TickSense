import matplotlib.pyplot as plt

def generate_chart(ticks, symbol):
    plt.figure()
    plt.plot(ticks[-50:])
    plt.title(symbol)
    filename = f"{symbol}.png"
    plt.savefig(filename)
    plt.close()
    return filename
