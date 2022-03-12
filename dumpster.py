                    # if the current item already has a price in the prices map, the price is updated
                    if index in prices:
                        if prices[index][0] > auction['starting_bid']:
                            prices[index][1] = prices[index][0]
                            prices[index][0] = auction['starting_bid']
                        elif prices[index][1] > auction['starting_bid']:
                            prices[index][1] = auction['starting_bid']
                    # otherwise, it's added to the prices map
                    else:
                        prices[index] = [auction['starting_bid'], float("inf")]

                    # if the auction fits in some parameters
                    if prices[index][1] > LOWEST_PRICE and prices[index][0]/prices[index][1] < LOWEST_PERCENT_MARGIN and auction['start']+60000 > lastUpdated:
                        results.append([auction['uuid'], auction['item_name'], auction['starting_bid'], index])